#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
from mpl_toolkits.axes_grid1 import host_subplot
import mpl_toolkits.axisartist
import matplotlib.pyplot as plt
import matplotlib as mpl
from os import makedirs

mpl.style.use('seaborn-bright')#'fivethirtyeight')
mpl.rcParams['figure.figsize'] = (17, 5)
mpl.rcParams['lines.linewidth'] = 2


'''
    Plot a graph. Variable number of axes, linked (or not). Lots of lovely options.
'''
def graph(x_data, y_data, *args, **kwargs):

    # Pop arguments
    title = kwargs.pop('title', None)            # string
    x_label = kwargs.pop('x_label', None)        # string
    y_label = kwargs.pop('y_label', None)        # string
    y_series = kwargs.pop('y_series', None)      # list of strings
    ylim = kwargs.pop('ylim', None)              # tuple OR list of tuples
    yscale = kwargs.pop('yscale', None)          # list of strings or string        ACCEPTS: [‘linear’ | ‘log’ | ‘logit’ | ‘symlog’]
    plot_func = kwargs.pop('plot_func', None)    # list of strings (function names)
    colors = kwargs.pop('colors', graph.colors)  # list of strings (colours)
    legend = kwargs.pop('legend', None)          # boolean
    twin_x = kwargs.pop('twin_x', None)          # boolean
    twin_y = kwargs.pop('twin_y', None)          # boolean
    savefig = kwargs.pop('savefig', None)        # boolean
    savedir = kwargs.pop('savedir', '.')         # str

    ## Closures
    # Return orientation (left or right) for in-order axis
    def orient(i,flip=0):
        return ("right" if (i+flip)%2 else "left")

    # Offset mapping: 
    # 0=>0, 1=>0, 2=>-50, 3=>50, 4=>-100, 5=>100, 6=>-150, etc
    def offset(i):
        return (offset.multiplier * (i//2)) * ((i%2) + (((i+1)%2))*-1)
    offset.multiplier = 60

    host = host_subplot(111, axes_class=mpl_toolkits.axisartist.Axes)
    host.axis["top"].toggle(all=False)

    # Iterate series
    for i in range(0, len(y_data)):
        if twin_x:
            ax = (host if (i==0) else host.twinx())
        elif twin_x and twin_y:
            ax = (host if (i==0) else host.twinx().twiny())
        else:
            ax = host

        label = y_series[i] if y_series is not None else ''

        if i>1 and twin_x and not twin_y:
            new_ax = ax.get_grid_helper().new_fixed_axis
            ax.axis[orient(i)] = new_ax(loc=orient(i), axes=ax, offset=(offset(i), 0))
            ax.axis[orient(i)].toggle(all=True) 
            ax.axis[orient(i,1)].toggle(all=False)

        if plot_func and plot_func[i] == 'vlines':
            p = ax.vlines(x_data[i] if type(x_data) is list else x_data, 
                          [0], 
                          y_data[i]*20, 
                          label=label, 
                          color=colors[i%len(colors)], 
                          zorder=-1, lw=5)

            ax.set_ylim(0,1)
            ax.axis[orient(i)].toggle(all=False)

        else:
            p, = ax.plot(x_data[i] if type(x_data) is list else x_data, 
                         y_data[i], label=label, color=colors[i%len(colors)])

            for t in ax.get_yticklabels():             # This doesn't work and I don't know why.
                t.set_color(colors[i%len(colors)])     #p.get_color())

            if ylim:     # Accept either a list or a tuple for ylim
                if type(ylim) is tuple:
                    ax.set_ylim(*ylim)
                elif (type(ylim) is list) and (ylim[i] is not None):
                    ax.set_ylim(*ylim[i])

            if yscale:
                if type(yscale) is list:
                    ax.set_yscale(yscale[i])
                elif type(yscale) is str:
                    ax.set_yscale(yscale)

        if not twin_y:
            ax.axis[orient(i)].label.set_color(colors[i%len(colors)])     #p.get_color())
            ax.set_ylabel(label)

    if title:
        t = plt.suptitle(title)
        t.set_fontsize(t.get_fontsize()+8)

    if x_label:
        host.set_xlabel(x_label)

    if y_label:
        host.set_ylabel(y_label)

    if legend:
        plt.legend()

    plt.draw()
    plt.show()

    if savefig:
        makedirs(savedir, exist_ok=True)
        plt.savefig("{0}/{1}.png".format(savedir, title))

# Statics
# Tableau20 colour scheme
graph.colors = ["#1f77b4", "#aec7e8", "#ff7f0e", "#ffbb78", "#2ca02c", "#98df8a", "#d62728", 
                 "#ff9896", "#9467bd", "#c5b0d5", "#8c564b", "#c49c94", "#e377c2", "#f7b6d2", 
                 "#7f7f7f", "#c7c7c7", "#bcbd22", "#dbdb8d", "#17becf", "#9edae5"]


'''
    Test operation
'''
def test():
    import numpy as np
    n=10000

    graph(np.array(range(0,n)),
        [ np.sort(np.random.normal(0, 0.2, size=n)),
          np.sort(np.random.power(0.1, size=n)),
          np.sort(np.random.random(size=n)) ], 
        x_label="n", 
        title="Graph test with Matplotlib (probabilities)",
        y_series=["Normal", "Power", "Random"], 
        twin_x=True, legend=True)


if __name__ == "__main__":
    test()
