#!/bin/bash

export PYTHONPATH="./tests:/usr/local/lib/python3.14/site-packages"

exec python3 -m unittest discover -s /Users/donato/Stagewarden/tests
