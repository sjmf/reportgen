#!/usr/bin/env python3
# coding: utf-8
import os
import sys
import argparse
import base64
import jinja2
import logging
import mimetypes
import weasyprint
import pandas as pd

import datahandling as dh
import graphing as gr
from graphing import weekly_graph, monthly_graph

# Tell me what you're doing, scripts :)
log = logging.getLogger(__name__)

template_dir = os.path.join(sys.path[0], "templates")


#
# Generate a report PDF from an input BAX datafile list
#
def report(input_datafiles, **kwargs):

    # Parse arguments
    output_pdf = bool(kwargs.pop('pdf', True)) and not bool(kwargs.pop('htm', False))

    output_file = kwargs.pop('output_file', 'out.pdf')
    map_filename = kwargs.pop('map_filename', None)
    description = kwargs.pop('description', None)
    location = kwargs.pop('location', None)
    threshold = kwargs.pop('threshold', None)
    series = kwargs.pop('series', None)
    names = kwargs.pop('names', None)
    plot_months = kwargs.pop('months', None)
    drop_subnet = kwargs.pop('drop_subnet', None)
    drop_sensors = kwargs.pop('drop_sensors', None)

#    log.debug("File list: " + '\n'.join(input_datafiles))

    # Perform data read-in using the datahandling module and apply corrections
    df, dfs, t_start, t_end = dh.read_data(input_datafiles, exclude_subnet=drop_subnet, exclude_sensors=drop_sensors)
    log.info("Data files range from {0} to {1}".format(t_start, t_end))

    if names:
        name_map = dh.read_sensor_names(names)      # Read in names
        dfs = dh.apply_sensor_names(dfs, name_map)  # Apply names
        log.debug(name_map)

    # Threshold sensors
    dfs = dh.threshold_sensors(dfs, threshold)

    # Print statistics
    sensor_stats(dfs)

    # Set sensible matplotlib defaults for plotting graphs
    gr.set_mpl_params()

    # Generate graphs using matplotlib for the following types:
    periods = get_month_range(df) if plot_months else get_week_range(df)

    # Types: a data type. (1, 2) where 1 is the pandas column in the DF and 2 is the series label
    types = [("Temp", "Temperature ˚C"), ("Humidity", "Humidity %RH"),
             ("Light", "Light (lux)"), ("PIRDiff", "Movement (PIR counts per minute)"),
             ("RSSI", "RX Signal (dBm)"), ("Battery", "Battery level (mV)")]

    if series:
        s_list = ['temperature', 'humidity', 'light', 'movement', 'rssi', 'battery']
        types = [types[i] for i, t in enumerate(s_list) if t in series]

    log.debug(types)
    log.info("Generating graphs for period {0} to {1}".format(periods[0][0], periods[-1:][0][0]))

    # TODO: Replace this call with a multiprocessing threadpool + map?
    # Single-threaded: 46.72s
    # *typestring: (series, y_label) from types array
    # *period: (t_start, t_end)
    figs = [[
            monthly_graph(dfs, *typestring, *p) if plot_months else
            weekly_graph(dfs, *typestring, *p, legend_cols=1 if names else 3)
            for p in periods
        ] for typestring in types]

# e.g. ('Light',
#       'Light (lux)',
#       Timestamp('2014-12-29 00:00:00', offset='W-MON'),
#       Timestamp('2015-01-04 00:00:00', offset='W-MON')),

#    from functools import partial
#    series = sum([[( dfs, *typestring, *period ) for period in weeks] for typestring in types ],[])
#    start_time = time.time()

# Plotting graphs this way gives an error:
# The process has forked and you cannot use this CoreFoundation functionality safely. You MUST exec().
# Break on __THE_PROCESS_HAS_FORKED_AND_YOU_CANNOT_USE_THIS_COREFOUNDATION_FUNCTIONALITY___YOU_MUST_EXEC__() to debug.

#    p = multiprocessing.Pool()
#    figs = p.map(plot_weekly, series)
#    log.info("+ Graphs generated in {0:.2f}s".format(time.time() - start_time))

    # Format graphs and metadata into a data structure for the jinja2 templater
    # Generates a structure of the form: to_plot[week][series][data]
    # e.g. to_plot[0][0]['label'] == 'Temperature ˚C'
    to_plot = [
        [
            {
                'type':     t,
                'label':    l,
                'data':     d[i],
                't_start':  w[0].date(),
                't_end':    w[1].date()
            } for i, w in enumerate(periods)
        ] for t, l, d in zip(*zip(*types), figs)
    ]

    # Read in the map
    loc_map = None
    if map_filename is not None:
        loc_map = read_map(map_filename)
        log.debug('map type is ' + str(loc_map[1]))

    output = render_template(
        weeks=periods,
        to_plot=to_plot,
        location=location,
        description=description,
        map=dict(zip(['b64', 'mime'], loc_map)) if map_filename is not None and loc_map[1] is not None else None
    )

    log.debug(output[:150].replace('\n', ' '))

    log.info("Writing to {1} file {0}".format(output_file, ('PDF' if output_pdf else 'HTM')))

    if output_pdf:
        # write to PDF
        print_css = weasyprint.CSS(os.path.join(template_dir, "report.css"))
        # debug_css = weasyprint.CSS(os.path.join(template_dir, "debug.css"))
        htm = weasyprint.HTML(string=output, base_url='.')
        htm.write_pdf(target=output_file, zoom=2, stylesheets=[print_css])  # , debug_css])

    else:
        # write to HTML:
        with open(output_file, 'w+') as t:
            t.write(output)


#
# Print some statistics about sensors, and drop those with only one packet
#
def sensor_stats(dfs):

    log.info(" ID      | Packets ")
    log.info("=========|=========")
    for k, df in dfs.items():
        log.info("{0:8} | {1}".format(k[:8], len(dfs[k])))

    return dfs


#
# Generate date range of weeks inclusive of start and end
#
def get_week_range(df):
    weeks = [
        (w, w + pd.DateOffset(days=6) + pd.Timedelta('23:59:59'))
        for w in list(df.groupby(pd.TimeGrouper(freq='W-MON', closed='left', label='left')).groups)
    ]

    # Skip weeks with no data
    weeks = [w if sum([len(df.loc[w[0]:w[1]])]) > 0 else None for w in weeks]
    weeks = [k for k in weeks if k is not None]

    return weeks


#
# Generate date range of months inclusive of start and end
#
def get_month_range(df):
    from pandas.tseries.offsets import MonthEnd, MonthBegin

    return [
        (m + MonthBegin(), m + MonthEnd() + pd.Timedelta('23:59:59'))
        for m in list(df.groupby(pd.TimeGrouper(freq='M', closed='left', label='left')).groups)
    ]


#
# Read a map (image file) and base64 encode it for the template
#
def read_map(map_filename):
    try:
        with open(map_filename, 'rb') as t:
            log.debug("Reading map: '"+map_filename+"'")
            return (
                base64.b64encode(t.read()).decode('utf8').replace('\n', ''),
                mimetypes.guess_type(map_filename)[0]
            )
    except (FileNotFoundError, TypeError):
        log.error("Map not found: '"+map_filename+"'")
        return None, None


#
# Render template to html and return a string
#
def render_template(weeks, **kwargs):
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=template_dir))
    return env.get_template('output.htm').render(
        **kwargs,
        period=(weeks[0][0].date().strftime('%d %b'), weeks[-1:][0][0].date().strftime('%d %b'))
    )


# Main function: parse command line arguments
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Handle arguments
    parser = argparse.ArgumentParser(description='Generate a report PDF from an input BAX datafile')

    # Required args:
    parser.add_argument("input_datafiles", nargs='+', action="store", type=str, help="Input file path list (CSV or BIN BAX data)")

    # Optional args
    parser.add_argument("--outfile",     "-o", dest="output_file",  action="store", type=str, default='out.pdf', help="Output file path (report)")
    parser.add_argument("--map",         "-m", dest="map_filename", action="store", type=str, help="Image file path")
    parser.add_argument("--location",    "-l", dest="location",     action="store", type=str, help="Location name string, e.g. 'Open Lab'")
    parser.add_argument("--description", "-d", dest="description",  action="store", type=str, help="Verbose description to add to report")
    parser.add_argument("--names",       "-n", dest="names",        action="store", type=str, help="File containing sensor name mappings")
    parser.add_argument("--drop_subnet", "-b", dest="drop_subnet",  action="store", type=str, help="Exclude subnet from sensor names")
    parser.add_argument("--threshold",   "-t", dest="threshold",    action="store", type=int, default=1, help="Discard sensors with fewer packets than threshold")
    parser.add_argument("--months",      "-a", dest="months",       action="store_true",      help="Plot months instead of weeks")
    parser.add_argument("--drop_sensors","-z", nargs='+', type=str, action="store", help="List of sensors to exclude from report")
    parser.add_argument("--series",      "-s", nargs='+', type=str, default=['temperature', 'humidity', 'light'])

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--pdf", action="store_true", default=True, help="Output a PDF file")
    group.add_argument("-k", "--htm", action="store_true", default=False, help="Output hypertext markup")

    parser.add_argument('--verbose', '-v', dest="verbose", action="count")

    # Parse 'em 
    args = parser.parse_args()

    # Logging
    strh = logging.StreamHandler()
    # Verbose logging 
    if args.verbose:
        if args.verbose >= 1:
            strh.setLevel(logging.DEBUG)
            logging.getLogger(__name__).setLevel(logging.DEBUG)
            log.debug("Verbosity: 1")
        if args.verbose >= 2:
            logging.getLogger('datahandling').setLevel(logging.DEBUG)
            log.debug("Verbosity: 2")
        if args.verbose >= 3:
            logging.getLogger('graphing').setLevel(logging.DEBUG)
            log.debug("Verbosity: 3")

    # Run report on the input args (with sensible default series)
    log.debug(vars(args))
    report(**vars(args))

