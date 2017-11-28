#!/usr/bin/env python3
# coding: utf-8
#
# A set of functions for generating aggregate statistics from BAX sensor data
#
# ## List of desired statistics:
#
# * Table with total monthly aggregates (for each month):
#   * Warmest, Coldest (mean, min, max)  ✅
#   * Dryest, wettest sensor (..)        ✅
#   * Brightest, darkest avg sensor (..) ✅
# * Range - difference between min and max, also min/max average ✅
# * 9-5 (working hours) aggregates       ✅
# * Average mean of all sensors (day, week, month)
# * Sensors w/ best / worst signal strength
# * Sensors requiring battery replacement (~2.2V)
#
import logging
import pandas as pd
import numpy as np
import datahandling as dh
from flask_table import NestedTableCol, Table, Col, create_table
from report import sensor_stats

# Set up logging
log = logging.getLogger(__name__)


# Default range for data considered to be within "working hours"
WORK_HOURS = ('09:00', '17:00')

# Operations to run on the aggregated data to pull out interesting stats:
DEFAULT_OPERATIONS = [
    ("Temp", "mean", "idxmax", "Warmest average"),
    ("Temp", "max", "idxmax", "Warmest overall"),
    ("Temp", "mean", "idxmin", "Coldest average"),
    ("Temp", "min", "idxmin", "Coldest overall"),
    ("Temp", "range", "idxmin", "Largest difference"),

    ("Humidity", "mean", "idxmax", "Humidest average"),
    ("Humidity", "max", "idxmax", "Humidest overall"),
    ("Humidity", "mean", "idxmin", "Dryest average"),
    ("Humidity", "min", "idxmin", "Dryest overall"),

    ("Light", "mean", "idxmax", "Brightest average"),
    ("Light", "max", "idxmax", "Brightest overall"),
    ("Light", "mean", "idxmin", "Darkest average"),
    ("Light", "min", "idxmin", "Darkest overall")
]


#
# Extract statistics from aggregated table
#
def extract_stats(agg, operations=DEFAULT_OPERATIONS):

    results = {}
    for time_period in agg.index.levels[0]:
        log.debug("{0:%B %Y}".format(time_period))  # TODO: Cope with weeks being passed
        sub_frame = agg.loc[time_period]
        
        stats = {}
        for op in operations:
            series, agg_val, operation, label = op

            name = getattr(sub_frame[(series, agg_val)], operation)()
            value = sub_frame.loc[name][(series, agg_val)]

            log.debug("{0}: ({1}) - {2} @ {3:.1f}".format(series, label, name, value))
            if series not in stats:
                stats[series] = []
                
            stats[series].append((label, name, value))
            
        log.debug("\n")
        results[time_period] = stats

    return results


#
# Construct and return a table using Flask-Table
#
def get_table(headers, items, name):

    ItemTable = create_table(name+'Table', base=Table)
    for h in headers:
        ItemTable.add_column(h, Col(h))

    # Populate, construct & return the table
    return ItemTable(items)


# Transpose a list of lists:
def transpose(l): 
    return list(map(list, zip(*l)))


# Function to calculate range (where x is a series)
def find_range(x):
    return np.ptp(x)


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

    df, dfs, t_start, t_end = dh.read_data(argv)
    dfs = dh.threshold_sensors(dfs, 100)

    # ##  Aggregation  ##

    # Overwrite `df` as dfs contains all the fixes:
    df = pd.concat(dfs.values())

    # Limit to values during working hours:
    df = df.iloc[df.index.indexer_between_time(WORK_HOURS[0], WORK_HOURS[1], include_start=True, include_end=True)]

    # Perform multi-column aggregation
    agg = df.groupby([pd.Grouper(freq='M'), 'Name']).agg({
        'Temp': ['mean', 'min', 'max', find_range],
        'Humidity': ['mean', 'min', 'max', find_range],
        'Light': ['mean', 'min', 'max'],
        'Battery': ['min']
    }).rename(columns={'find_range': 'range'})

    stats = extract_stats(agg)

    # Iterate each month
    for month in list(stats.keys()):

        # Mung data until it looks good for tabulation:
        container = {}
        for series in stats[month]:
            internal = stats[list(stats.keys())[0]][series]
            internal = transpose(internal)
            headers = internal[0]
            internal = [dict(zip(headers, v)) for v in internal[1:]]

            table = get_table(headers, internal, series)
            container[series] = table

        # Tabulate the data:
        # create a nested table using NestedTableCol
        TopTable = create_table('TopTable', base=Table)
        for series in container:
            TopTable.add_column(series.lower() + '_table', NestedTableCol(series, container[series].__class__))

        items = [{series.lower() + '_table': container[series].items for series in container}]

        table = TopTable(items)

        show(table.__html__())

        # TODO: Create Jinja2 template and populate with tables

    # return table


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    import sys
    test(sys.argv)

