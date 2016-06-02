#!/usr/bin/env python3
# coding: utf-8
import argparse, base64, calendar, jinja2, logging, mimetypes, multiprocessing, time, weasyprint
import matplotlib as mpl
import pandas as pd

import datahandling as dh
from graphing import plot_weekly, weekly_graph

# Tell me what you're doing, scripts :)
log = logging.getLogger(__name__)

template_dir = "templates/"

'''
    Generate a report PDF from an input BAX datafile list
'''
def report(input_datafiles, output_filename, *args, **kwargs):

    # Parse arguments
    output_pdf = bool(kwargs.pop('pdf'))
    output_htm = bool(kwargs.pop('htm'))

    map_filename = kwargs.pop('map_filename', None)
    description = kwargs.pop('description')
    location = kwargs.pop('location')
    series = kwargs.pop('series', None)

    log.info("File list: "+ '\n'.join(input_datafiles))

    # Perform data read-in using the datahandling module and apply corrections
    df, dfs, t_start, t_end = read_data(input_datafiles)
    log.info("Data files range from {0} to {1}".format(t_start, t_end))
    
    sensor_stats(dfs)

    # Set sensible matplotlib defaults for plotting graphs
    set_mpl_params()

    # Generate graphs using matplotlib for the following types:
    weeks = get_week_range(t_start, t_end, df)
    # Types: a data type. (1, 2) where 1 is the pandas column in the DF and 2 is the series label
    types = [("Temp", "Temperature ˚C"), ("Humidity", "Humidity %RH"), 
             ("Light", "Light (lux)"), ("PIRDiff", "Movement (PIR counts per minute)"), 
             ("RSSI", "RX Signal (dBm)")]

    if series:
        s_list = ['temperature','humidity','light','movement','rssi']
        types = [ types[i] for i,t in enumerate(s_list) if t in series ]
    else:
        types = types[3:] # only temp + humid + light by default

    log.debug(types)
    log.info("Generating graphs for period {0} to {1}".format(weeks[0][0], weeks[-1:][0][0]))

    # TODO: Replace this call with a multiprocessing threadpool + map?
    # Single-threaded: 46.72s
    figs  = [ [weekly_graph( dfs, *typestrings, *period ) for period in weeks] for typestrings in types ]
#    from functools import partial

    # e.g. ('Light', 'Light (lux)', Timestamp('2014-12-29 00:00:00', offset='W-MON'), Timestamp('2015-01-04 00:00:00', offset='W-MON')),
#    series = sum([[( dfs, *typestrings, *period ) for period in weeks] for typestrings in types ],[])

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
                'type'    : t,
                'label'   : l,
                'data'    : d[i],
                't_start' : w[0].date(),
                't_end'   : w[1].date()
            } for i,w in enumerate(weeks)
        ] for t,l,d in zip(*zip(*types), figs)
    ]

    # Read in the map 
    if map_filename:
        loc_map = read_map(map_filename)
        log.debug('map type is '+ str(loc_map[1]))

    output = render_template(
        weeks=weeks,
        to_plot=to_plot,
        location=location,
        description=description,
        map=dict(zip(['b64', 'mime'],loc_map))
                if map_filename and loc_map[1] else None
    )

    log.debug(output[:150].replace('\n', ' '))

    log.info( "Writing to {1} file {0}".format(output_filename,('HTM' if output_htm else 'PDF')) )
    if output_htm:
        # write to HTML:
        with open(output_filename, 'w+') as t: t.write(output)
    else:
        # write to PDF
        print_css = weasyprint.CSS(template_dir+"report.css")
        debug_css = weasyprint.CSS(template_dir+"debug.css")
        htm = weasyprint.HTML(string=output, base_url='.')
        pdf = htm.write_pdf(target=output_filename, zoom=2, stylesheets=[print_css])#, debug_css])


'''
    Print some statistics about sensors, and drop those with only one packet
'''
def sensor_stats(dfs):
    for k in list(dfs.keys()):
        if len(dfs[k]) <= 1:
            log.warn("Dropping sensor {}: too few packets".format(k))
            dfs.pop(k, None)

    log.info(" ID      | Packets ")
    log.info("=========|=========")
    for k,df in dfs.items():
        log.info("{0:8} | {1}".format(len(dfs[k]), k))

    return dfs


'''
    Set appropriate matplotlib parameters
'''
def set_mpl_params():
    mpl.style.use('seaborn-bright')#'fivethirtyeight')
    mpl.rcParams['lines.linewidth'] = 1
    mpl.rcParams['figure.figsize'] = (8,12) #(3,2)
    mpl.rcParams['axes.titlesize'] = 'large'
    mpl.rcParams['axes.labelsize'] = 'small'
    mpl.rcParams['xtick.labelsize'] = 'small'
    mpl.rcParams['ytick.labelsize'] = 'small'
    mpl.rcParams['legend.fontsize'] = 'small'
    mpl.rcParams['legend.frameon'] = False
    mpl.rcParams['savefig.dpi'] = 100.0
    mpl.rcParams['font.size'] = 10.0


'''
    Generate date range of weeks inclusive of start and end
'''
def get_week_range(t_start, t_end, df):
    weeks = [
        day for day in pd.date_range(
            (t_start - pd.Timedelta('7 days')), t_end + pd.Timedelta('7 days'), 
            freq='W-MON', 
            normalize=True, 
            closed=None
        )
    ]
    weeks = [(start,end- pd.Timedelta('1 day')) for start,end in zip(weeks,weeks[1:])]
    # Skip weeks with no data
    weeks = [ w if sum( [len( df.loc[w[0]:w[1]] )] ) > 0 else None for w in weeks ]
    weeks = [ k for k in weeks if k is not None ]
    return weeks


'''
    Read a map (image file) and base64 encode it for the template
'''
def read_map(map_filename):
    try:
        with open(map_filename, 'rb') as t:
            log.debug("Reading map: '"+map_filename+"'")
            return (
                base64.b64encode(t.read()).decode('utf8').replace('\n',''),
                mimetypes.guess_type(map_filename)[0]
            )
    except (FileNotFoundError, TypeError):
        log.error("Map not found: '"+map_filename+"'")
        return (None,None)


'''
    Read a BuildAX datafile. Accept:
       * List of datafiles
    and return:
       * a Pandas DataFrame with corrections applied
       * start and end date/time values for the period
'''
def read_data(input_datafiles):
    pd.set_option('chained_assignment', None) # Hush up, SettingWithCopyWarning

    start_time = time.time()
    # Use a generator to concatenate datafiles into a list 
    # Single threaded: 60.73 seconds 
    #df = pd.concat( (dh.readfile(infile) for infile in input_datafiles) )

    # Multithreaded:  19.43 seconds. Winner!
    p = multiprocessing.Pool()
    df = pd.concat( p.map(dh.readfile, input_datafiles) )
    
    log.info("+ Data read in {0:.2f}s".format(time.time() - start_time))

    # Extract sensor IDs / names and split into dict by sensor ID
    t_start, t_end = (df.index.min(), df.index.max())
    names = dh.unique_sensors(df)
    dfs = dh.split_by_id(df)

    # Apply fixes to the data and diff the PIR movement
    dfs = dh.clean_data(dfs)

    return (df, dfs, t_start, t_end)


'''
    Render template to html and return a string
'''
def render_template(weeks, **kwargs):
    env = jinja2.Environment( loader=jinja2.FileSystemLoader(searchpath='./templates') )
    return env.get_template('output.htm').render(
        **kwargs,
        period = ( weeks[0][0].date().strftime('%d %b'), weeks[-1:][0][0].date().strftime('%d %b') )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Handle arguments
    parser = argparse.ArgumentParser(description='Generate a report PDF from an input BAX datafile')

    # Required args:
    parser.add_argument("input_datafiles", nargs='+', action="store", type=str, help="Input file path list (CSV or BIN BAX data)")
    parser.add_argument("output_filename", action="store", type=str, help="Output file path (PDF report)")

    # Optional args
    parser.add_argument("--map",         dest="map_filename", action="store", type=str, help="Image file path")
    parser.add_argument("--location",    dest="location",     action="store", type=str, help="Location name string, e.g. 'Open Lab'")
    parser.add_argument("--description", dest="description",  action="store", type=str, help="Verbose description to add to report")

    group = parser.add_mutually_exclusive_group()
    group.add_argument("-p", "--pdf", action="store_true", default=False, help="Output a PDF file")
    group.add_argument("-k", "--htm", action="store_true", default=False, help="Output hypertext markup")

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
            logging.getLogger('datahandling.py').addHandler(strh)
        if args.verbose >= 3:
            logging.getLogger('graphing.py').addHandler(strh)
            logging.getLogger('graphing.py').setLevel(logging.INFO)

    # Run report on the input args
    log.debug(vars(args))
    report(**vars(args))

