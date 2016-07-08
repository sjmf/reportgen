#!/usr/bin/env python3
# coding: utf-8
import mpl_toolkits.axisartist
import matplotlib.pyplot as plt
import pandas as pd
import base64
import calendar
import logging

from mpl_toolkits.axes_grid1 import host_subplot
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

        plt.savefig(
            handle,
            format='svg',
            transparent=True,
            # bbox_inches='tight',
            pad_inches=0)

        handle.seek(0)
        return base64.b64encode(handle.getvalue()).decode('utf-8').replace('\n', '')
    else:
        plt.show()


#
# Plot a series as weekly views using subplots
#
def weekly_graph(dfs, series, y_label, t_start, t_end, **kwargs):
    # Argument sanity check
    if t_end - t_start > pd.Timedelta('6 days'):
        raise ValueError("Date range passed is > 1 week: {0} to {1}".format(t_start, t_end))

    rows = 4
    cols = 2
    colors = kwargs.pop('colors', graph.colors)
    # Eight subplots, returned as a 2-d array
    fig, axarr = plt.subplots(rows, cols, sharey=True)
    fig.subplots_adjust(hspace=0, wspace=0)
    fig.autofmt_xdate()

    from matplotlib.ticker import MaxNLocator
    plt.gca().yaxis.set_major_locator(MaxNLocator(prune='both'))

    log.info("{0: <8} - {1} to {2}".format(series, str(t_start), str(t_end)))

    i = 1
    for day in pd.date_range(t_start, t_end, freq='D', normalize=True):
        start, end = (day, (day + pd.Timedelta('1 day')))
        row, col = (i // cols, i % cols)
        ax = axarr[row, col]

        # Pandas Data
        x_data = [dfs[i].loc[start:end, ].index for i in dfs]
        y_data = [dfs[i].loc[start:end, series].values for i in dfs]

        # Ignore days with one value (e.g. fetch interface returns 23:59:58 from the previous day)
        #        if sum( [len(x) for x in x_data] ) <= len( x_data ):
        #            log.debug("Skipping {0} as not enough data".format(t_start))
        #            continue

        log.debug("Graphing {0} in cell {1} @{2},{3}".format(t_start, i, row, col))

        for j in range(0, len(y_data)):
            # log.debug(str(j) + ',' + str(len(x_data)) + ',' + str(len(y_data)) + ',' + str(row) + ',' + str(col))
            ax.plot(x_data[j], y_data[j], color=colors[j % len(colors)])

        # Force 24h graph time period
        ax.set_xlim(start, end)

        ax.set_title(
            # 'Axis [{0},{1}]'.format(row, col),
            "{0} {1}".format(calendar.day_abbr[start.dayofweek], start.date().strftime('%d %b')),
            loc='left', x=0.05, y=0.80)

        ax.grid(alpha=0.25)

        # ax.text(3, 2, 'hiya')
        i += 1

    # Fine-tune figure
    # Set labels on left column plots y-axis
    for row in range(0, rows):
        axarr[row, 0].set_ylabel(y_label)

        for col in range(0, cols):
            axarr[row, col].tick_params(
                axis='both',  # changes apply to both axis
                which='both',  # both major and minor ticks are affected
                bottom='off',  # ticks along the bottom edge are off
                top='off',  # ticks along the top edge are off
                left='off',
                right='off',
                labelbottom='on')  # labels along the bottom edge are on

    # Plot a legend inside the upper leftmost figure
    leg = plt.figlegend(
        handles=axarr[0, 1].lines,
        labels=list(dfs.keys()),
        loc='upper left',
        bbox_to_anchor=(0.13, -0.1, 1, 1),
        bbox_transform=plt.gcf().transFigure,
        ncol=3,
        labelspacing=0.5,
        columnspacing=0.25,
        markerscale=2,
        frameon=False)
    plt.setp(leg.get_lines(), linewidth=1.5)  # the legend linewidth

    # Output to buffer using savefig
    output = BytesIO()
    plt.savefig(
        output,
        format='svg',
        transparent=True,
        bbox_inches='tight',
        pad_inches=0.1)

    output.seek(0)
    b64 = base64.b64encode(output.getvalue()).decode('utf-8').replace('\n', '')

    # Explicitly close plot to stop ipython complaining about memory
    # (this also stops ipython displaying plots, but who cares)
    fig.clf()
    plt.close()

    return b64


#
# Alias of weekly_graph() which expands a tuple to the arguments:
#   dfs, series, y_label, t_start, t_end:
#
def plot_weekly(t):
    return weekly_graph(*t)


#
# Test operation
#
def test():
    import numpy as np
    n = 10000

    multiaxis_graph(np.array(range(0, n)),
                    [np.sort(np.random.normal(0, 0.2, size=n)),
                     np.sort(np.random.power(0.1, size=n)),
                     np.sort(np.random.random(size=n))],
                    x_label="n",
                    title="Graph test with Matplotlib (probabilities)",
                    y_series=["Normal", "Power", "Random"],
                    twin_x=True, legend=True)


# Main operation
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    strh = logging.StreamHandler()
    strh.setLevel(logging.DEBUG)
    log.addHandler(strh)

    test()
