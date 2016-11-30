#!/usr/bin/env python3
# Call me with file arguments to process and output them as a unified CSV
# (including fixes for PIR)
import os, sys
import logging
import argparse
import pandas as pd
import datahandling as dh
from report import sensor_stats, read_data

# Tell me what you're doing, scripts :)
log = logging.getLogger(__name__)

template_dir = os.path.join(sys.path[0], "templates")

#
# Read files, fix them, write them out
#
def process(input_datafiles, output_file, **kwargs):
    log.info("File list: " + '\n'.join(input_datafiles))
    
    if os.path.isfile(output_file): 
        log.error("Output filename already exists, exiting")
        sys.exit(1)

    # Perform data read-in using the datahandling module and apply corrections
    df, dfs, t_start, t_end = read_data(input_datafiles)
    log.info("Data files range from {0} to {1}".format(t_start, t_end))

    sensor_stats(dfs)
    
    log.info("Sorting data to write out...")

    out = pd.concat([dfs[d] for d in dfs])
    out.sort_index(inplace=True)
    out.fillna(0, inplace=True)
    out.to_csv(output_file, header=True)

    log.info("Done! Output written to {}".format(output_file))

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Handle arguments
    parser = argparse.ArgumentParser(description='Generate a report PDF from an input BAX datafile')
    # Required args:
    parser.add_argument("input_datafiles", nargs='+', action="store", type=str, help="Input file path list (CSV or BIN BAX data)")
    # Optional args
    parser.add_argument("-o", "--out", dest="output_file", action="store", default='out.csv', help="Output file")
    parser.add_argument('--verbose', '-v', action='count')

    # Parse 'em 
    args = parser.parse_args()

    # Logging
    strh = logging.StreamHandler()
    # Verbose logging 
    if args.verbose:
        if args.verbose >= 1:
            strh.setLevel(logging.DEBUG)
        if args.verbose >= 2:
            logging.getLogger('report.py').addHandler(strh)
            logging.getLogger('datahandling.py').addHandler(strh)

    # Run report on the input args (with sensible default series)
    log.debug(vars(args))
    process(**{**vars(args)})


