#!/usr/bin/env python3
#
import pandas as pd
import numpy as np
import logging
import mimetypes
import subprocess

# Add error logging
log = logging.getLogger('datahandling.py')
strh = logging.StreamHandler()
strh.setLevel(logging.DEBUG)
log.addHandler(strh)

# Global variables
TOOLS_DIR = "/Users/sam/Code/embedded/BuildAX/Software/Release/"

# STFU SettingWithCopyWarning
pd.set_option('chained_assignment', None)


'''
    Read a BAX file and save it into Pandas' data structure
'''
def readfile(filename):
    # Guess which method to use based on file mimetype
    mtype = mimetypes.guess_type(filename)
    log.info(mtype)

    # Binary BAX file (convert first)
    if mtype[0] is None:
        return df_from_bin(filename)
    elif 'text' in mtype[0]:
        return df_from_csv(filename)



'''
    Call the BAXTest utility (compiled) to read binary files
'''
def df_from_bin(filename, decryption_keys=None):

    proc = subprocess.Popen([
        TOOLS_DIR + "BAXTest",
        "-Sf",                                           # Source:        file
        "-D"+filename,                                   # Descriptor:    filename
        "-Fu",                                           # Format:        units (binary)
        "-Er",                                           # Encoding:      raw binary
        "-Os",                                           # Output:        stdout
        "-Mc",                                           # Mode (output): CSV
        "-I"+decryption_keys if decryption_keys else ''  # Info file:     decryption_keys
    ],stdout=subprocess.PIPE)

    return df_from_csv(proc.stdout)



'''
    Using pandas, parse a BAX dataframe from the given descriptor
'''
def df_from_csv(file_descriptor):

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
        ))

    # Drop encrypted rows
    df.dropna(inplace=True)

    df.index.names = ['DateTime']
    return df



'''
    Extract individual sensors to a list
'''
def unique_sensors(df):
    return df.Name.unique()



'''
    Split a dataframe by the sensor ID and return a mapping
'''
def split_by_id(df):
    return { n: df.loc[df.Name == n,:] for n in df.Name.unique() }



'''
    Return a tuple with the first and last date values
'''
def date_range(df):
    return (df.index.min(), df.index.max())



'''
    Apply PIR fix to DataFrame:
    Fast PIR Differencing using Pandas array operations
'''
def diff_pir(dfs):
    ಠ_ಠ = 1e9 # scale factor to use
    σ = 5     # detect trigger above 5σ standard deviations

    for i in dfs:
        d = dfs[i].loc[:,['PIREnergy']]

            # Time deltas
        df_time = pd.DataFrame(d.index, index=d.index)    \
                .diff().fillna(0)                         \
                .div(np.timedelta64(1,'s'))               \
                .astype('int64')

        # Differentiate & fix wrapping at 2^16, 
        # then normalize to 0 and apply scale factor
        df_diff = d['PIREnergy'].diff()                   \
                .apply(lambda x: x if x > 0 else x+65535) \
                .astype('float')                          \
                .div(df_time['DateTime']                  \
                        .astype('float'),axis='index')    \
                .diff() * ಠ_ಠ

        # Calculate std. deviation
        df_std = pd.rolling_std(df_diff, window=250) * σ

        # Event triggers
        df_event = (df_diff > df_std).to_frame(name='Event')

        # Store views into original DataFrame
        dfs[i].loc[:,'Event'] = df_event[df_event['Event']== True]
        dfs[i].loc[:,'PIRDiff'] = df_diff
        #dfs[i].loc[:,'PIRStd'] = df_std

    return dfs



'''
    Apply fix to broken values at high humidity
'''
def fix_humidity(dfs):
    # Constants from Analog.c
    lookup = np.array([
        [   0,  18168,  25600   ], #  5˚C
        [   8,  19092,  25600   ], # 10˚C
        [   10, 19761,  26195   ], # 15˚C
        [   14, 20480,  26819   ], # 20˚C
        [   18, 21662,  26819   ], # 25˚C
        [   23, 22086,  27473   ], # 30˚C
        [   28, 22528,  28160   ], # 35˚C
        [   34, 23467,  28160   ], # 40˚C
        [   40, 23966,  28882   ], # 45˚C
        [   45, 24487,  28882   ], # 50˚C
        [   51, 24487,  28882   ], # 55˚C
        [   54, 25031,  29642   ]])

    # Pre-compute interpolation skew
    temp2index = np.array([  5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60  ])
    temp_humid_skews = [ (t[-1] - t[0]) / (t[-1] - t[-2]) for t in lookup ]

    # Stateful function to determine overflowed values
    def humidity_needsfix(x):
        if x[2] < 55 and (humidity_needsfix.broken or np.mean(x[:2])>80):
            humidity_needsfix.broken = True
            return True
        humidity_needsfix.broken = False
        return False

    # static var used for state on humidity_needsfix closure
    humidity_needsfix.broken = False

    # Conditionally 'fix' incorrect values
    def fix_humidity_values(d):
        temp_index = min(max(0, np.floor(d.Temp/5)-1),11)
        return min( 90 + ((55 - d.Humidity) / temp_humid_skews[temp_index]), 100 )

    for i in dfs:
        df = dfs[i]
        # Determine if overflowing with window (this value low, previous values high)
        needsFix = pd.rolling_apply(df[['Humidity']], window = 5, func = humidity_needsfix, center = True).loc[:,'Humidity']
        # Apply fix to affected rows using temperature adjustment
        df.loc[needsFix>0,'Humidity'] = df.loc[needsFix>0][['Temp','Humidity']].apply(fix_humidity_values, axis = 1)

    return dfs


'''
    Apply division by 10 to temperature values (in-place)
'''
def fix_temp(dfs):
    for i in dfs:
        dfs[i].loc[:,'Temp'] = dfs[i].loc[:,'Temp'].div(10)
    return dfs


'''
    Produce a graph for a given datatype and time range
'''
def graph(datatype, timerange):
    pass



'''
    Test operation
'''
def test():
    # Read file
    #df = readfile("./testdata/fetch.bax")
    #df = readfile("./testdata/fetch.bax.0.csv")

    df = readfile("./testdata/LOG00001.TXT")
    names = unique_sensors(df)
    dfs = split_by_id(df)
    dfs = fix_humidity(dfs)
    dfs = diff_pir(dfs)

    print(dfs[names[0]].dtypes.index)
    print(names)
    print(date_range(df))



if __name__ == "__main__":
    test()

