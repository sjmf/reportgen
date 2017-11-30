#!/usr/bin/env python3
# coding: utf-8
#
# A set of functions for generating aggregate statistics from BAX sensor data
#
# ## List of desired statistics:
#
# * Table with total monthly aggregates (for each month):
#   * Warmest, Coldest (mean, min, max)             ✅
#   * Dryest, wettest sensor (..)                   ✅
#   * Brightest, darkest avg sensor (..)            ✅
# * Range - difference between min and max          ✅
# * 9-5 (working hours) aggregates                  ✅
# * Average mean of all sensors (day, week, month)
# * Sensors w/ best / worst signal strength
# * Sensors requiring battery replacement (~2.2V)
# * Decimal place formatting (1dp)                  ✅
#
import logging
import pandas as pd
import numpy as np
import datahandling as dh
from flask_table import NestedTableCol, Table, Col, create_table

# Set up logging
log = logging.getLogger(__name__)


# Default range for data considered to be within "working hours"
WORK_HOURS = ('09:00', '17:00')

# Operations to run on the aggregated data to pull out interesting stats:
DEFAULT_OPERATIONS = {
    # Series : column |operation |label
    "Temp": [("mean",  "idxmax", "Warmest average"),
             ("max",   "idxmax", "Maximum temperature"),
             ("mean",  "idxmin", "Coldest average"),
             ("min",   "idxmin", "Minimum temperature"),
             ("range", "idxmax", "Temperature range")],

    "Humidity": [("mean", "idxmax", "Humidest average"),
                 ("max",  "idxmax", "Maximum humidity"),
                 ("mean", "idxmin", "Dryest average"),
                 ("min",  "idxmin", "Minimum humidity")],

    "Light": [("mean", "idxmax", "Brightest average"),
              ("max",  "idxmax", "Maximum brightness"),
              ("mean", "idxmin", "Darkest average"),
              ("min",  "idxmin", "Minimum brightness")],

    # "Battery": [("min", "idxmin", "Lowest battery")]
}


#
# Extract statistics from aggregated table
#
def extract_stats(agg, operations=DEFAULT_OPERATIONS):

    results = {}
    for time_period in agg.index.levels[0]:
        log.debug("{0:%B %Y}".format(time_period))  # TODO: Cope with weeks being passed
        sub_frame = agg.loc[time_period]

        stats = {}
        for series in operations:
            if series not in stats:
                stats[series] = []

            for agg_val, operation, label in operations[series]:

                name = getattr(sub_frame[(series, agg_val)], operation)()
                value = sub_frame.loc[name][(series, agg_val)]

                log.debug("{0}: ({1}) - {2} @ {3:.1f}".format(series, label, name, value))

                stats[series].append((label, name, '{0:.1f}'.format(value)))

        log.debug("\n")
        results[time_period] = stats

    return results


#
# Perform multi-column aggregation
#
def aggregate(df: pd.DataFrame, freq='M'):
    return df.groupby([pd.Grouper(freq=freq), 'Name']).agg({
        'Temp': ['mean', 'min', 'max', find_range],
        'Humidity': ['mean', 'min', 'max', find_range],
        'Light': ['mean', 'min', 'max'],
        'Battery': ['min']
    }).rename(columns={'find_range': 'range'})


#
# Construct and return a table using Flask-Table
#
def get_table(headers, items, name):

    table = create_table(name+'Table', base=Table)
    for h in headers:
        table.add_column(h, Col(h))

    # Populate, construct & return the table
    return table(items)


#
# Transpose a list of lists
#
def transpose(l: list):
    return list(map(list, zip(*l)))


#
# Function to calculate range (where x is a series)
#
def find_range(x):
    return np.ptp(x)


#
# Limit dataframe to values within the passed hours only
#
def limit_by_hours(df: pd.DataFrame, t_start=WORK_HOURS[0], t_end=WORK_HOURS[1]):
    return df.iloc[df.index.indexer_between_time(t_start, t_end, include_start=True, include_end=False)]


#
# Perform tabulation of data to html <table>
#
def tabulate(stats):

    # create a nested table using NestedTableCol
    TopTable = create_table('TopTable', base=Table)

    # Mung data until it looks good for tabulation:
    items = {}
    for series in stats:
        t_data = transpose(stats[series])                       # Transpose row/col ordering
        headers = t_data[0]                                     # Separate out headers
        t_data = [dict(zip(headers, v)) for v in t_data[1:]]    # Separate the rest of the rows
        items[series.lower() + '_table'] = t_data               # Store items for table construction
        table = get_table(headers, t_data, series)              # Construct sub-table class

        # Tabulate the data: add column to top-level table for this series
        TopTable.add_column(series.lower() + '_table', NestedTableCol(dh.TYPE_LABELS[series], table.__class__))

    return TopTable([items])


#
# Test aggregation functionality
#
def test(argv):

    # Display html table in the system default browser
    def show(out):
        import webbrowser
        import base64

        out = base64.b64encode(out.encode('utf-8')).decode('utf-8').replace('\n', '')
        webbrowser.open_new_tab("data:text/html;charset=UTF-8;base64," + out)

    # Read in data
    df, dfs, t_start, t_end = dh.read_data(argv, exclude_subnet="42")
    dfs = dh.threshold_sensors(dfs, 100)
    df = pd.concat(dfs.values())     # Overwrite `df` as dfs contains all the fixes

    # ##  Aggregation  ##
    # Limit to values during working hours:
    df = limit_by_hours(df, WORK_HOURS[0], WORK_HOURS[1])

    # Perform multi-column aggregation and
    #  extract interesting stats from the aggregate table
    stats = extract_stats(aggregate(df, freq='M'))

    # Iterate each month and tabulate each stats set
    table_list = [tabulate(stats[month]) for month in list(stats.keys())]

    # ===============================================
    # Create Jinja2 template and populate with tables
    import jinja2
    import os

    template_dir = os.path.join(sys.path[0], "templates")
    environment = jinja2.Environment(loader=jinja2.FileSystemLoader(searchpath=template_dir))

    def datetimeformat(value, format='%H:%M / %d-%m-%Y'):
        return value.strftime(format)

    # register it on the template environment by updating the filters dict:
    environment.filters['datetimeformat'] = datetimeformat

    html = environment.get_template('aggregates.htm').render({
        'table_list': zip(list(stats.keys()), table_list),
    })

    show(html)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    import sys
    test(sys.argv)

