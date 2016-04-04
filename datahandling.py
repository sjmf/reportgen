#!/usr/bin/env python3
#
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
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

    df.index.names = ['DateTime']
    return df


'''
    Extract individual sensors to a list
'''
def unique_sensors(df):
    return df.Name.unique()


'''
    Return a tuple with the first and last date values
'''
def date_range(df):
    return (df.index.min(), df.index.max())


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

    print(df)
    print(df.dtypes.index)
    print(unique_sensors(df))
    print(date_range(df))


if __name__ == "__main__":
    test()

