#!/bin/bash

export PYTHONPATH="./tests:/usr/local/lib/python3.14/site-packages"

# Execute tests with verbosity and capture output disabled
exec python3 -m unittest discover -v -s /Users/donato/Stagewarden/tests
