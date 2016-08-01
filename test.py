#!/usr/bin/env python3
# coding: utf-8
import datahandling
import graphing
import report
import logging
import gc
import objgraph
import os
import sys
import glob

log = logging.getLogger(__name__)
DATA_ROOT = "/Users/sam/Dropbox/PhD/BuildAX/"

DATAFILES = [
    (glob.glob(DATA_ROOT + "Lancaster/bins/*"),
     "Lancaster University"),
    ([DATA_ROOT + "Drummond/data/split/5th Floor.csv"],
     "Drummond 5F"),
    ([DATA_ROOT + "Drummond/data/split/Ground Floor.csv"],
     "Drummond GF"),
    ([DATA_ROOT + "AndyG-house/data.csv"],
     "Andy's House"),
    ([DATA_ROOT + "Auditing-Data/ceam.csv"],
     "CEAM Study Room"),
    ([DATA_ROOT + "Burnside/data/BF-block3.csv"],
     "Burnside Cooking Rooms"),
    ([DATA_ROOT + "CORE building data/openlab-bax-6.csv"],
     "CORE building"),
]
DATAFILES = DATAFILES[1:2]
TEST_PATH = 'test_output'
object_counts = []


# Run tests
def test():

    datahandling.test(DATAFILES[0][0][0])

    graphing.test()


def report_test():
    os.makedirs(TEST_PATH, exist_ok=True)
    print_memory('pre')

    for i, line in enumerate(DATAFILES):

        objgraph.show_growth(limit=3)

        input_files, location = line[0], line[1]
        report_name = TEST_PATH + '/test_' + str(i) + '.pdf'

        log.info(input_files)
        log.info(location)
        log.info(report_name)

        try:
            report.report(input_files, report_name, location=location)

            log.info("Report saved to {}".format(report_name))

        except Exception as e:
            log.exception("Exception occurred when reporting (test failed):")

        print_memory(i)

    plot_object_counts()


def print_memory(i):
    global object_counts

    print("\n\n--------------------- MEMORY -------------------------\n")

    print("TOTAL OBJECTS\n")
    o = len(gc.get_objects())
    print(o)
    object_counts.append(o)
    del o
    print("\n")

    print("GROWTH\n")
    objgraph.show_growth()
    print("\n")

    print("COMMON TYPES\n")
    objgraph.show_most_common_types()
    print("\n")

    print("LEAKING OBJECTS\n")
    roots = objgraph.get_leaking_objects()
    print("\n")

    log.info("ROOTS pre-collect : {}\n".format(len(roots)))

    print("COMMON TYPES IN ROOTS\n")
    objgraph.show_most_common_types(objects=roots)
    print("\n")

    objgraph.show_refs(roots[:3], refcounts=True, filename=TEST_PATH + '/roots_' + str(i) + '.png')
    print("\n")

    log.info("Garbage pre collect:  " + str(len(gc.garbage)))
    gc.collect()
    log.info("Garbage post collect: " + str(len(gc.garbage)))
    print("\n")

    roots = objgraph.get_leaking_objects()
    log.info("ROOTS post-collect : {}".format(len(roots)))

    print("\n\n---------------------------------------------------\n")


def plot_object_counts():
    import matplotlib.pyplot as plt
    plt.plot(object_counts)
    plt.ylabel('Object Counts')
    plt.show()


# Setup logging and run tests
if __name__ == "__main__":

    # Verbose logging
    logging.basicConfig(level=logging.DEBUG)

    strh = logging.StreamHandler(sys.stdout)
    strh.setLevel(logging.DEBUG)

    fmt = logging.Formatter('%(message)s')
    strh.setFormatter(fmt)

    [log.removeHandler(h) for h in log.handlers]
    log.handlers = []
    log.propagate = False
    log.addHandler(strh)

    logging.getLogger('report.py').addHandler(strh)
    logging.getLogger('report.py').setLevel(logging.INFO)

    logging.getLogger('datahandling.py').addHandler(strh)
    logging.getLogger('datahandling.py').setLevel(logging.INFO)

    # logging.getLogger('graphing.py').addHandler(strh)
    logging.getLogger('graphing.py').setLevel(logging.WARN)

    report_test()
