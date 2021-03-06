#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 
import pandas as pd
import numpy as np
import multiprocessing
import time
import logging
import mimetypes
import subprocess
import os

log = logging.getLogger(__name__)

# Global variables
TOOLS_DIR = os.environ.get('BAX_TOOLS_DIR', os.path.join(os.environ['HOME'], 'baxsw/Release'))
if not os.path.isfile(os.path.join(TOOLS_DIR, "BAXTest")):
    raise FileNotFoundError("BuildAX tooling missing in {}".format(TOOLS_DIR))


# Types: a data type. (1, 2) where 1 is the pandas column in the DF and 2 is the series label
TYPE_LABELS = {
    'Battery': 'Battery level (mV)',
    'Humidity': 'Humidity %RH',
    'Light': 'Light (lux)',
    'PIRDiff': 'Movement (PIR counts per minute)',
    'RSSI': 'RX Signal (dBm)',
    'Temp': 'Temperature ˚C'
}


#
# Read a BuildAX datafile. Accept:
#     * List of datafiles
#  and return:
#     * a Pandas DataFrame with corrections applied
#   * start and end date/time values for the period
#
def read_data(input_datafiles: list, exclude_subnet=None, exclude_sensors=None, skip_humidity=False):

    if type(input_datafiles) is str:
        raise TypeError("String passed to read_data function instead of list of strings")

    pd.set_option('chained_assignment', None)  # Hush up, SettingWithCopyWarning

    start_time = time.time()
    # Use a generator to concatenate datafiles into a list
    # Single threaded: 60.73 seconds
    # df = pd.concat( (dh.readfile(infile) for infile in input_datafiles) )

    # Multithreaded:  19.43 seconds. Winner!
    p = multiprocessing.Pool()
    df = pd.concat(p.map(readfile, input_datafiles))

    log.info("Running final sort on merge...")
    df.sort_index(inplace=True)  # Sort again on merge

    # Lots of subprocesses hanging around: clean 'em up:
    log.info("Waiting for subprocesses to finish...")
    p.close()
    p.join()

    log.info("+ Data read in {0:.2f}s".format(time.time() - start_time))

    start_time = time.time()
    log.info("+ Applying data fixes")

    # Extract sensor IDs / names and split into dict by sensor ID
    t_start, t_end = (df.index.min(), df.index.max())

    # Fix names (decode from unicode and ensure same case before splitting / dropping)
    fix_names(df)

    # Drop a subset of sensors from the dataframe?
    if exclude_sensors is not None:
        drop_sensors(df, exclude_sensors)

    # Exclude subnet from sensor IDs?
    if exclude_subnet is not None:
        drop_subnet(df, exclude_subnet)

    # Split into multiple dataframes by id
    dfs = split_by_id(df)

    # Apply fixes to the data and diff the PIR movement
    dfs = clean_data(dfs, skip_humidity)

    # Overwrite `df` as dfs contains all the fixes
    df = pd.concat(dfs.values())

    log.info("+ Data fixes applied in {0:.2f}s".format(time.time() - start_time))

    return df, dfs, t_start, t_end


#
# Read a BAX file and save it into Pandas' data structure
#
def readfile(filename):
    log.info("Reading data from {0}".format(filename))

    # Guess which method to use based on file mimetype
    mtype, _ = mimetypes.guess_type(filename)
    log.debug("Detected MIME: {0}".format(mtype))

    # Plaintext BAX file
    try:
        if mtype and 'text' in mtype:
            return df_from_csv(filename)
        else:  # Binary (convert first)
            return df_from_bin(filename)
    except TypeError as e:
        log.error("File not found: {}".format(filename))
        log.error(e)


#
# Call the BAXTest utility (compiled) to read binary files
#
def df_from_bin(filename, decryption_keys=None):

    log.debug("Decoding data file from binary")
    proc = subprocess.Popen([
        os.path.join(TOOLS_DIR, "BAXTest"),
        "-Sf",                                           # Source:        file
        "-D"+filename,                                   # Descriptor:    filename
        "-Fu",                                           # Format:        units (binary)
        "-Er",                                           # Encoding:      raw binary
        "-Os",                                           # Output:        stdout
        "-Mc",                                           # Mode (output): CSV
        "-Pd",                                           # Packets:       decrypted only
        "-I"+decryption_keys if decryption_keys else ''  # Info file:     decryption_keys
    ], stdout=subprocess.PIPE)

    return df_from_csv(proc.stdout)


#
# Using pandas, parse a BAX dataframe from the given descriptor
#
def df_from_csv(file_descriptor):

    log.debug("Reading CSV from filehandle: {0}".format(file_descriptor))
    df = pd.read_csv(
        filepath_or_buffer=file_descriptor,
        parse_dates=[['Date', 'Time']],
        index_col=0,
        names=(
            'Date',
            'Time',
            'Name',
            'RSSI',
            'Type',
            'SequenceNo',
            'TransmitPower',
            'Battery',
            'Humidity',
            'Temp',
            'Light',
            'PIRCount',
            'PIREnergy',
            'Switch'
        ),
        dtype={
            'Name':'S8'
        }
    )

    # Drop encrypted rows
    log.debug("Dropping encrypted rows...")
    df.dropna(inplace=True)

    # Sort to prevent "ValueError: index must be monotonic increasing or decreasing"
    log.debug("Sorting by time index...")
    df.sort_index(inplace=True)

    df.index.names = ['DateTime']
    return df


#
# Read sensor data from CSV file formatted as the following:
#     SENSORID,SensorName
# Accept:
#   * Filename
# Return:
#   * dict() object mapping sensor IDs to names
def read_sensor_names(sensor_file):
    import csv
    with open(sensor_file) as f:
        return dict(csv.reader(f))


#
# Replaces the keys of the dfs with the names specified in file
# Caller is responsible for ensuring there are no conflicts as
# this involves reversing a mapping
def apply_sensor_names(dfs, name_map):
    return {name_map[k]: v for k, v in dfs.items()}


#
# Extract individual sensors to a list
#
def unique_sensors(df):
    return [name.upper() for name in df.Name.unique()]


#
# Threshold sensors: remove sensors with fewer packets than the given threshold
#
def threshold_sensors(dfs, threshold=1):
    # Iterate over the sensors in dfs and drop the bad ones
    for k in list(dfs.keys()):
        if len(dfs[k]) <= threshold:
            log.warning("Dropping sensor {0}: {1} packets <= threshold {2}".format(k, len(dfs[k]), threshold))
            dfs.pop(k, None)

    return dfs


#
# Split a dataframe by the sensor ID and return a mapping
#
def split_by_id(df, id_column='Name'):
    # Return mapping of name to (sub)dataframe
    return {n: df.loc[df[id_column] == n, :] for n in df[id_column].unique()}


#
# Fix dataframe 'Name' labels to ensure all are the same case and datatype
#
def fix_names(df, name_column='Name'):
    # Make sure all the names are the same case for comparison!
    # By using .loc we ensure this happens in-place (not on a copy)
    df.loc[:, name_column] = df[name_column].apply(lambda name: name.upper().decode("utf-8"))


#
# Return a tuple with the first and last date values
#
def date_range(df):
    return df.index.min(), df.index.max()


#
# Apply PIR fix to DataFrame:
# Fast PIR Differencing using Pandas array operations
#
def diff_pir(dfs, σ=5, pir_threshold=1500):
    # detect trigger above 5σ standard deviations by default

    for i in dfs:
        d = dfs[i].loc[:, ['PIREnergy']]

        # Time deltas
        df_time = pd.DataFrame(d.index, index=d.index) \
            .diff().fillna(pd.Timedelta(seconds=0))    \
            .div(np.timedelta64(1, 's'))               \
            .astype('int64')

        # Differentiate & fix wrapping at 2^16,
        # then normalize to 0 and apply scale factor
        df_diff = d['PIREnergy'].diff()               \
            .apply(lambda x: x if x > 0 else x+65535) \
            .astype('float')                          \
            .div(df_time['DateTime'].astype('float'), axis='index') \
            .diff()

        # Calculate std. deviation
        df_std = df_diff.rolling(window=250, center=False).std() * σ

        # Event triggers
        df_event = (df_diff > df_std).to_frame(name='Event')

        # Store views into original DataFrame
        dfs[i].loc[:, 'Event'] = df_event # [df_event['Event'] == True]
        dfs[i].loc[:, 'PIRDiff'] = df_diff
        # dfs[i].loc[:,'PIRStd'] = df_std

    # Scrub erroneous values:
    for i in dfs:
        # Pull out view into dataframe, where rows are out of threshold, then zero them by updating the
        # original with a new zero-filled data frame matching those indices
        out_of_threshold = dfs[i][(dfs[i].PIRDiff > pir_threshold) | (dfs[i].PIRDiff < -pir_threshold)]
        zeroed_values = pd.DataFrame(0, index=out_of_threshold.index, columns=['PIRDiff'])
        dfs[i].update(zeroed_values)

    return dfs


#
# Apply fix to broken values at high humidity
#
def fix_humidity(dfs):
    # Constants from Analog.c
    lookup = np.array([
        [0,  18168,  2560],  # 05˚C
        [8,  19092,  2560],  # 10˚C
        [10, 19761,  2619],  # 15˚C
        [14, 20480,  2681],  # 20˚C
        [18, 21662,  2681],  # 25˚C
        [23, 22086,  2747],  # 30˚C
        [28, 22528,  2816],  # 35˚C
        [34, 23467,  2816],  # 40˚C
        [40, 23966,  2888],  # 45˚C
        [45, 24487,  2888],  # 50˚C
        [51, 24487,  2888],  # 55˚C
        [54, 25031,  2964]])

    # Pre-compute interpolation skew
    # temp2index = np.array([5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60])
    temp_humid_skews = [(t[-1] - t[0]) / (t[-1] - t[-2]) for t in lookup]

    # Stateful function to determine overflowed values
    def humidity_needsfix(x):
        if x[2] < 55 and (humidity_needsfix.broken or np.mean(x[:2]) > 80):
            humidity_needsfix.broken = True
            return True
        humidity_needsfix.broken = False
        return False

    # static var used for state on humidity_needsfix closure
    humidity_needsfix.broken = False

    # Conditionally 'fix' incorrect values
    def fix_humidity_values(d):
        temp_index = min(max(0, np.floor(d.Temp/5)-1), 11)
        return min(90 + ((55 - d.Humidity) / temp_humid_skews[temp_index]), 100)

    for i in dfs:
        df = dfs[i]

        # Determine if overflowing with window (this value low, previous values high)
        needs_fix = df[['Humidity']].rolling(
            window=5,
            center=True
        ).apply(
            func=humidity_needsfix
        ).loc[:, 'Humidity']

        # Apply fix to affected rows using temperature adjustment
        df.loc[needs_fix > 0, 'Humidity'] = df.loc[needs_fix > 0][['Temp', 'Humidity']] \
            .apply(fix_humidity_values, axis=1)

    return dfs


#
# Apply division by 10 to temperature values (in-place)
#
def fix_temp(dfs):
    for i in dfs:
        dfs[i].loc[:, 'Temp'] = dfs[i].loc[:, 'Temp'].div(10)
    return dfs


#
# Scrub erroneous values using light data
#
def fix_light(dfs):
    dfs = {i: dfs[i].drop(dfs[i][dfs[i].Light > 1500].index) for i in dfs}
    return dfs


#
# Drop the subnet from sensor addresses in a DataFrame
# (ensure fix_names has been called on the data first!)
#
def drop_subnet(df: pd.DataFrame, subnet: str):
    log.debug("Dropping subnet {} from sensor IDs".format(subnet))
    df.replace({"Name": {"^({0})".format(subnet): ""}}, regex=True, inplace=True)


#
# Drop the list of sensor IDs provided from the dataframe
# (ensure fix_names has been called on the data first!)
#
def drop_sensors(df: pd.DataFrame, sensor_list: list):
    log.debug("Dropping sensors: {}".format(", ".join(sensor_list)))
    df.drop(df[df['Name'].isin(sensor_list)].index, inplace=True)


#
# Limit range to scrub out-of-bounds values
#
def limit_range(dfs):
    for i in dfs:
        dfs[i].loc[:, 'Temp'] = dfs[i].loc[:, 'Temp']\
            .apply(lambda d: d if (d > -500) and (d < 1000) else np.NaN)
        
        dfs[i].loc[:, 'Humidity'] = dfs[i].loc[:, 'Humidity']\
            .apply(lambda d: d if (d > 0.0) and (d < 101.0) else np.NaN)

    return dfs


#
# Clean data: apply fixes and scrub erroneous values
#
def clean_data(dfs, skip_humidity=False, skip_light=False, skip_temperature=False, skip_pir=False):
    log.debug("Limiting range...")
    dfs = limit_range(dfs)

    if not skip_light:
        log.debug("Fixing light...")
        dfs = fix_light(dfs)

    if not skip_humidity:
        log.debug("Fixing humidity...")
        dfs = fix_humidity(dfs)

    if not skip_temperature:
        log.debug("Fixing temperature (/10)...")
        dfs = fix_temp(dfs)

    if not skip_pir:
        log.debug("Differencing PIR...")
        dfs = diff_pir(dfs)
    
    return dfs


#
# Test operation
#
def test(datafile):
    # Read file
    df, dfs, t_start, t_end = read_data([datafile], exclude_subnet="42")
    names = unique_sensors(df)

    log.info(dfs[names[0]].dtypes.index)
    log.info(names)
    log.info(date_range(df))


# Main operation: run test
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.DEBUG)

    test(sys.argv[1])
