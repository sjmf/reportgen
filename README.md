# BAX report generation toolkit

This repository contains a set of python3 tools for generating matplotlib-based
graphs from BuildAX datasets.

## Dependencies
BAXTest tooling from the openmovement repository:

```
    git clone https://github.com/digitalinteraction/baxTest.git
    make
```

## Example call:
```
~/Code/reportgen/report.py \
	--map ~/Dropbox/PhD/BuildAX/Cassie/maps/Ground\ floor\ Cassie\ 001.jpeg \
	--location "Cassie Ground Floor" \
    -p \
    ~/Dropbox/PhD/BuildAX/Cassie/split/Ground\ Floor.csv \
    ~/Dropbox/PhD/BuildAX/Cassie/Cassie_Ground.pdf
```

## APT deps
`apt-get install python-dev libxml2 libxml2-dev libxslt-dev`

## Python deps
Install these using `pip3 install -r conf/requirements.txt`. You may wish to
use a virtual environment like so:

```
    (sudo) pip3 install virtualenv
    python3 -m venv ENV
    . ./ENV/bin/activate
    pip3 install -r conf/requirements.txt
```

