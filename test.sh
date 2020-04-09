#!/bin/sh
rm -rf wheel2/*
./wgc2.py wheels/xlrd-1.2.0-py2.py3-none-any.whl wheel2 && cd wheel2 && unzip *.whl && zstd -d *.zst && unzip -v *.zip && echo "win"
