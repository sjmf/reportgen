#!/usr/bin/env python3
# coding: utf-8
import mpl_toolkits.axisartist
import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import base64
import calendar
import logging
import math

from mpl_toolkits.axes_grid1 import host_subplot
from matplotlib.ticker import MaxNLocator
from pandas.tseries.offsets import MonthEnd, MonthBegin
from datetime import datetime, timedelta
from io import BytesIO
from os import makedirs

log = logging.getLogger(__name__)


#
# Namespace for colors
def graph():
    pass


# Tableau20 colour scheme
graph.colors = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728",
                "#ff9896", "#9467bd", "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2",
                "#7f7f7f", "#c7c7c7", "#bcbd22", "#dbdb8d", "#17becf", "#9edae5"]


#
# Set appropriate matplotlib parameters
#
def set_mpl_params():
    mpl.style.use('seaborn-bright')  # 'fivethirtyeight')
    mpl.rcParams['lines.linewidth'] = 1
    mpl.rcParams['figure.figsize'] = (8, 12)  # (3,2)
    mpl.rcParams['axes.titlesize'] = 'large'
    mpl.rcParams['axes.labelsize'] = 'small'
    mpl.rcParams['xtick.labelsize'] = 'small'
    mpl.rcParams['ytick.labelsize'] = 'small'
    mpl.rcParams['legend.fontsize'] = 'small'
    mpl.rcParams['legend.frameon'] = False
    mpl.rcParams['savefig.dpi'] = 100.0
    mpl.rcParams['font.size'] = 10.0


#
# Output a plot to buffer using savefig
#
def save_figure(fig, handle):

    fig.savefig(
        handle,
        format='svg',
        transparent=True,
        bbox_inches='tight',
        pad_inches=0.1)

    handle.seek(0)
    return base64.b64encode(handle.getvalue()).decode('utf-8').replace('\n', '')


#
# Sort labels for legend
#
def get_sorted_labels(handles, labels):
    import operator
    hl = sorted(zip(handles, labels),
                key=operator.itemgetter(1))
    return zip(*hl)


#
# Manually calculate range of y-axis data
# This is a workaround for a bug: Setting xlim with plt.sublplots(..., sharey=True)
# causes the yaxis to center on 0 if plotted 2 plots with no y_data (0 range). Therefore,
# restrict the y-axis ticks manually using set_yticks and calculate the range pre-plot:
#
def get_yaxis_range(dfs, series, t_end, pad_pc=10):

    rng = list()
    for frame in dfs:
        try:
            mini = dfs[frame].groupby(pd.TimeGrouper(freq='M'))[series].agg(['min']) \
                .rename(columns={'min': series}).loc[t_end.date()][series]

            maxi = dfs[frame].groupby(pd.TimeGrouper(freq='M'))[series].agg(['max']) \
                .rename(columns={'max': series}).loc[t_end.date()][series]

            rng.append((mini, maxi))

        except KeyError as e:
            log.warning("Skipped {0} in range as there was no data for {1}".format(frame, t_end.date()))
            log.warning("The error was: {}".format(e))

    rng = list(zip(*rng))

    # Pad range by percentage:
    rng = [min(rng[0]), max(rng[1])]
    diff = rng[1] - rng[0]
    return [math.floor(rng[0] - (diff * (pad_pc / 100))), math.ceil(rng[1] + (diff * (pad_pc / 100)))]


#
# Alias of weekly_graph() which expands a tuple to the arguments:
#   dfs, series, y_label, t_start, t_end:
#
def plot_weekly(t):
    return weekly_graph(*t)


#
# Plot a graph. Variable number of axes, linked (or not). Lots of lovely options.
#
def multiaxis_graph(x_data, y_data, **kwargs):
    # Pop arguments
    title = kwargs.pop('title', None)  # string
    x_label = kwargs.pop('x_label', None)  # string
    y_label = kwargs.pop('y_label', None)  # string
    y_series = kwargs.pop('y_series', None)  # list of strings
    ylim = kwargs.pop('ylim', None)  # tuple OR list of tuples
    yscale = kwargs.pop('yscale', None)  # list of strings or string [‘linear’ | ‘log’ | ‘logit’ | ‘symlog’]
    plot_func = kwargs.pop('plot_func', None)  # list of strings (function names)
    colors = kwargs.pop('colors', graph.colors)  # list of strings (colours)
    legend = kwargs.pop('legend', None)  # boolean
    twin_x = kwargs.pop('twin_x', None)  # boolean
    twin_y = kwargs.pop('twin_y', None)  # boolean
    savefig = kwargs.pop('savefig', None)  # boolean or str (processed as filename)
    savedir = kwargs.pop('savedir', '.')  # str

    # Closures
    # Return orientation (left or right) for in-order axis
    def orient(x, flip=0):
        return "right" if (x + flip) % 2 else "left"

    # Offset mapping: 
    # 0=>0, 1=>0, 2=>-50, 3=>50, 4=>-100, 5=>100, 6=>-150, etc
    def offset(x):
        return offset.multiplier * (x // 2) * ((x % 2) + ((x + 1) % 2) * -1)

    offset.multiplier = 60

    plt.figure()
    host = host_subplot(111, axes_class=mpl_toolkits.axisartist.Axes)
    host.axis["top"].toggle(all=False)

    # Iterate series
    for i in range(0, len(y_data)):
        if twin_x:
            ax = (host if (i == 0) else host.twinx())
        elif twin_x and twin_y:
            ax = (host if (i == 0) else host.twinx().twiny())
        else:
            ax = host

        label = y_series[i] if y_series is not None else ''

        if i > 1 and twin_x and not twin_y:
            new_ax = ax.get_grid_helper().new_fixed_axis
            ax.axis[orient(i)] = new_ax(loc=orient(i), axes=ax, offset=(offset(i), 0))
            ax.axis[orient(i)].toggle(all=True)
            ax.axis[orient(i, 1)].toggle(all=False)

        if plot_func and plot_func[i] == 'vlines':
            ax.vlines(x_data[i] if type(x_data) is list else x_data,
                      [0],
                      y_data[i] * 20,
                      label=label,
                      color=colors[i % len(colors)],
                      zorder=-1, lw=5,
                      **kwargs)

            ax.set_ylim(0, 1)
            ax.axis[orient(i)].toggle(all=False)

        else:
            ax.plot(x_data[i] if type(x_data) is list else x_data,
                    y_data[i], label=label, color=colors[i % len(colors)],
                    **kwargs)

            for t in ax.get_yticklabels():  # This doesn't work and I don't know why.
                t.set_color(colors[i % len(colors)])  # p.get_color())

            # Accept either a list or a tuple for ylim:
            if ylim is not None:
                if type(ylim) is tuple:
                    ax.set_ylim(*ylim)
                elif (type(ylim) is list) and (ylim[i] is not None):
                    ax.set_ylim(*ylim[i])

            if yscale is not None:
                if type(yscale) is list:
                    ax.set_yscale(yscale[i])
                elif type(yscale) is str:
                    ax.set_yscale(yscale)

        if not twin_y:
            ax.axis[orient(i)].label.set_color(colors[i % len(colors)])
            ax.set_ylabel(label)

    if title:
        plt.suptitle(title)

    if x_label:
        host.set_xlabel(x_label)

    if y_label:
        host.set_ylabel(y_label)

    if legend:
        plt.legend()

    plt.draw()

    if savefig:
        if type(savefig) is str:
            makedirs(savedir, exist_ok=True)
            handle = "{0}/{1}".format(savedir, title if (type(savefig) is bool) else savefig)
        else:
            handle = BytesIO()

        return save_figure(plt, handle)
    else:
        plt.show()


#
# Plot a series as weekly views using subplots
#
def weekly_graph(dfs: dict,
                 series,
                 y_label,
                 t_start,
                 t_end,
                 cols=2,
                 legend_cols=3,
                 grid=True,
                 spline_alpha=0.1,
                 txt_alpha=0.6,
                 sort_legend=True,
                 **kwargs):

    # Argument sanity check
    if t_end - t_start > pd.Timedelta('7 days') - pd.Timedelta('1 microsecond'):
        raise ValueError("Date range passed is > 1 week: {0} to {1}".format(t_start, t_end))

    cells = 8
    rows = cells // cols
    colors = kwargs.pop('colors', graph.colors)
    spines = kwargs.pop('spines', {'top': True, 'bottom': True, 'left': True, 'right': True})

    # Eight subplots, returned as a 2-d array
    fig, axarr = plt.subplots(rows, cols, sharey=True)
    fig.subplots_adjust(hspace=0, wspace=0)
    fig.autofmt_xdate()

    # Reformat axarr for 1x8 or 8x1 plots
    if rows == 1:
        axarr = [axarr, []]
    if cols == 1:
        axarr = [[ax] for ax in axarr]

    plt.gca().yaxis.set_major_locator(MaxNLocator(prune='both'))

    log.info("{0: <8} - {1} to {2}".format(series, str(t_start), str(t_end)))

    # Start plotting at cell 1 (cell zero is legend)
    i = 1
    for day in pd.date_range(t_start, t_end, freq='D', normalize=True):
        start, end = (day, (day + pd.Timedelta('1 day')))
        row, col = (i // cols, i % cols)
        ax = axarr[row][col]

        # Pandas Data
        x_data = [dfs[i].loc[start:end, ].index for i in dfs]
        y_data = [dfs[i].loc[start:end, series].values for i in dfs]

        # Ignore days with one value (e.g. fetch interface returns 23:59:58 from the previous day)
        # if sum( [len(x) for x in x_data] ) <= len( x_data ):
        #     log.debug("Skipping {0} as not enough data".format(t_start))
        #     continue

        log.debug("Graphing {0} in cell {1} @{2},{3}".format(start.date().strftime('%d %b'), i, row, col))

        for j in range(0, len(y_data)):
            # log.debug(str(j) + ',' + str(len(x_data)) + ',' + str(len(y_data)) + ',' + str(row) + ',' + str(col))
            ax.plot(x_data[j], y_data[j], color=colors[j % len(colors)])

        # Force 24h graph time period
        ax.set_xlim(start, end)

        ax.set_title(
            # 'Axis [{0},{1}]'.format(row, col),
            "{0} {1}".format(calendar.day_abbr[start.dayofweek],
                             start.date().strftime('%d %b')),
            loc='left', x=0.05, y=0.80)

        if grid:
            ax.grid(alpha=0.25)

        # Set spines for this grid box (the outside lines)
        for sp in spines.keys():
            ax.spines[sp].set_visible(spines[sp])
            ax.spines[sp].set_alpha(spline_alpha)

        i += 1

        # Set text/label alpha
        [l.set_alpha(txt_alpha) for l in ax.xaxis.get_ticklabels()]
        [l.set_alpha(txt_alpha) for l in ax.yaxis.get_ticklabels()]

    # Set spines for legend cell
    for sp in spines.keys():
        axarr[0][0].spines[sp].set_visible(spines[sp])
        axarr[0][0].spines[sp].set_alpha(spline_alpha)

    # Fine-tune figure
    # Set labels on left column plots y-axis
    for row in range(0, rows):
        axarr[row][0].set_ylabel(y_label)

        for col in range(0, cols):
            axarr[row][col].tick_params(
                axis='both',  # changes apply to both axis
                which='both',  # both major and minor ticks are affected
                bottom='off',  # ticks along the bottom edge are off
                top='off',  # ticks along the top edge are off
                left='off',
                right='off',
                labelbottom='on')  # labels along the bottom edge are on

    # Get the handles and labels for a legend
    handles = axarr[0][1 if cols > 1 else 0].lines
    labels = list(dfs.keys())

    # sort legend by labels
    if sort_legend:
        handles, labels = get_sorted_labels(handles, labels)

    # Plot a legend inside the upper leftmost figure
    leg = plt.figlegend(
        handles,
        labels,
        loc='upper left',
        bbox_to_anchor=(0.13, -0.12, 1, 1),  # (left, bottom, width, height)
        bbox_transform=plt.gcf().transFigure,
        ncol=legend_cols,
        labelspacing=0.5,
        columnspacing=0.25,
        markerscale=2,
        frameon=False)

    plt.setp(leg.get_lines(), linewidth=1.5)  # the legend linewidth

    b64 = save_figure(fig, handle=BytesIO())

    # Explicitly close plot to stop ipython complaining about memory
    # (this also stops ipython displaying plots, but who cares)
    fig.clf()
    plt.close()

    return b64


#
# Plot a monthly view of the data
#
def monthly_graph(dfs: dict,
                  series,
                  y_label,
                  t_start,
                  t_end,
                  cols=1,
                  legend_rows=None,
                  grid=True,
                  spline_alpha=0.1,
                  txt_alpha=0.6,
                  sort_legend=True,
                  **kwargs):

    # Argument sanity check
    if t_start + MonthEnd() > t_end + MonthBegin():
        raise ValueError("Date range passed is > 1 month: {0} to {1}".format(t_start, t_end))

    # Clamp range: always display the whole month regardless of the data passed
    t_start = t_start + pd.Timedelta('1 microsecond') - MonthBegin()
    t_end = t_end - pd.Timedelta('1 microsecond') + MonthEnd()

    # Calculate date range and required cells
    date_range = pd.date_range(t_start - pd.Timedelta('7 days'), t_end,
                               freq='W-MON', normalize=True, closed=None, label='left')
    cells = len(date_range)
    rows = cells // cols
    legend_cols = len(dfs) // legend_rows + 1 if legend_rows else 6

    colors = kwargs.pop('colors', graph.colors)
    spines = kwargs.pop('spines', {'top': True, 'bottom': True, 'left': True, 'right': True})
    hspace = kwargs.pop('hspace', 0)
    wspace = kwargs.pop('wspace', 0)
    pad_pc = kwargs.pop('pad_pc', 10)

    rng = get_yaxis_range(dfs, series, t_end, pad_pc)

    # Subplots, returned as a 2-d array
    fig, axarr = plt.subplots(rows, cols)
    fig.subplots_adjust(hspace=hspace, wspace=wspace)
    fig.autofmt_xdate()

    # Reformat axarr for 1x8 or 8x1 plots
    if rows == 1:
        axarr = np.array([axarr, []])
    if cols == 1:
        axarr = np.array([[ax] for ax in axarr])

    # Commented out as without sharey=True different ticks are sometimes generated
    # plt.gca().yaxis.set_major_locator(MaxNLocator(prune='both'))

    log.info("{0: <8} - {1} to {2}".format(series, str(t_start), str(t_end)))

    # Start plotting at cell 1 (cell zero is legend)
    i = 0
    for week in date_range:

        start, end = (week, (week + pd.Timedelta('7 days')))
        row, col = (i // cols, i % cols)
        log.debug("{},{}".format(row, col))
        ax = axarr[row][col]

        # Pandas Data
        x_data = [dfs[i].loc[start:end, ].index for i in dfs]
        y_data = [dfs[i].loc[start:end, series].values for i in dfs]

        cardinality = sum([len(y) for y in y_data])
        log.info("Graphing {0} in cell {1} @{2},{3} ({4} values)"
                 .format(start.date().strftime('%D %b'),
                         i, row, col, cardinality))

        # Iterate sensors
        for j in range(0, len(y_data)):
            ax.plot(x_data[j], y_data[j], color=colors[j % len(colors)])

        # Set graph limits
        ax.set_autoscale_on(False)
        ax.set_xlim(start, end)
        ax.set_ylim(rng[0], rng[1])

        ax.set_title(
            # 'Axis [{0},{1}]'.format(row, col),
            start.date().strftime('%d %b'),
            loc='left', x=0.025, y=0.80)

        if grid:
            ax.grid(True, which="both", alpha=0.25)

        # Set spines for this grid box (the outside lines)
        for sp in spines.keys():
            ax.spines[sp].set_visible(spines[sp])
            ax.spines[sp].set_alpha(spline_alpha)

        # Set text/label alpha
        [l.set_alpha(txt_alpha) for l in ax.xaxis.get_ticklabels()]
        [l.set_alpha(txt_alpha) for l in ax.yaxis.get_ticklabels()]

        # Operations on the final (bottom) x axis row
        if row == rows - 1:
            weekday_map = {0: 'MON', 1: 'TUE', 2: 'WED', 3: 'THU', 4: 'FRI', 5: 'SAT', 6: 'SUN'}

            # Map weekdays to timestamps to match the correct day of the week (trimming last label)
            xs = sorted(ax.get_xticks())
            wd = pd.DatetimeIndex(pd.date_range(start=start, end=end, freq='D')).map(pd.Timestamp.weekday).values[:-1]

            ax.set_xticks(xs)
            ax.set_xticks([], minor=True)
            ax.set_xticklabels([weekday_map[d] for d in wd])

        # Fine-tune figure
        # Set labels on left column plots y-axis
        # Turn off y-axis tick labels in columns that aren't leftmost:
        if col > 0:
            [i.set_visible(False) for i in ax.yaxis.get_ticklabels()]
        else:  # elif col == 0:
            ax.set_ylabel(y_label)

        # Fine-tune ticks
        ax.tick_params(
            axis='both',  # changes apply to both axis
            which='both',  # both major and minor ticks are affected
            bottom='off',  # ticks along the bottom edge are off
            top='off',  # ticks along the top edge are off
            left='off',
            right='off',
            labelbottom='on')  # labels along the bottom edge are on

        i += 1

    # Leftover cell?
    while i < cells:
        row, col = (i // cols, i % cols)
        ax = axarr[row][col]
        log.debug("Leftover cell")

        # Set spines for this grid box (the outside lines)
        for sp in spines.keys():
            ax.spines[sp].set_visible(spines[sp])
            ax.spines[sp].set_alpha(spline_alpha)

        ax.xaxis.get_ticklabels()[i].set_visible(False)

        i += 1

    # Get the handles and labels for a legend
    handles = axarr[0][1 if cols > 1 else 0].lines
    labels = list(dfs.keys())

    # sort legend by labels
    if sort_legend:
        handles, labels = get_sorted_labels(handles, labels)

    # Plot a legend inside the upper leftmost figure
    leg = fig.legend(
        handles,
        labels,
        loc='upper left',
        bbox_to_anchor=(0.12, -.06, 1, 1),  # (left, bottom, width, height)
        bbox_transform=plt.gcf().transFigure,
        ncol=legend_cols,
        labelspacing=0.5,
        columnspacing=0.5,
        markerscale=2,
        frameon=False)

    if leg is not None:
        plt.setp(leg.get_lines(), linewidth=1.5)  # the legend linewidth

    b64 = save_figure(fig, handle=BytesIO())

    # Explicitly close plot to stop ipython complaining about memory
    fig.clf()
    plt.close()

    return b64


#
# Test operation
#
def test():
    import random
    random.seed(123456)

    # Generate test data for temporal graph types
    def gen_test_data(nsensors=10):
        import string

        def get_test_id():
            sample = string.hexdigits[:10] + string.hexdigits[-6:]
            return "42" + "".join([random.choice(sample) for _ in range(6)])

        def get_test_data(ndays=100):
            date_start = datetime.now() - pd.Timedelta(str(ndays) + ' days')

            df = pd.DataFrame({'date': [date_start + timedelta(hours=x) for x in range(ndays * 24)],
                               'test': pd.Series(np.random.randn(ndays * 24))})
            return df.set_index('date')

        return {get_test_id(): get_test_data() for _ in range(nsensors)}

    # Display the graph in the system default browser
    def show(svg):
        import webbrowser
        webbrowser.open_new_tab("data:image/svg+xml;charset=UTF-8;base64," + svg)


    # Test multiaxis graph:
    n = 10000
    svg = multiaxis_graph(np.array(range(0, n)),
                    [np.sort(np.random.normal(0, 0.2, size=n)),
                     np.sort(np.random.power(0.1, size=n)),
                     np.sort(np.random.random(size=n))],
                    x_label="n",
                    title="Graph test with Matplotlib (probabilities)",
                    y_series=["Normal", "Power", "Random"],
                    twin_x=True, legend=True, savefig=True)
    show(svg)

    # Gen data to test temporal graphs
    set_mpl_params()
    dfs = gen_test_data(nsensors=10)
    when = datetime.combine(datetime.now().date(), datetime.min.time())

    # Test weekly graph and open the result in the browser
    svg = weekly_graph(dfs, 'test', 'Test Data', when - pd.Timedelta('6 days'), when)
    show(svg)

    # Test monthly graph:
    svg = monthly_graph(dfs, 'test', 'Test Data', when, when + MonthEnd(), hspace=.1)
    show(svg)


# Main operation
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    strh = logging.StreamHandler()
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)

    test()
