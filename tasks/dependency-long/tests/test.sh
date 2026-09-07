#!/bin/sh
set -eu
python -I /tests/grader.py /tests/spec.json /app
