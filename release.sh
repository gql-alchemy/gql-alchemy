#!/usr/bin/env bash

rm dist/*
python3.6 setup.py sdist
python3.6 setup.py bdist_wheel
twine upload dist/*
