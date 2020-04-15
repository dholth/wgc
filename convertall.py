#!/bin/python
import glob
import wgc2
from pathlib import Path

if False:
    """
real    0m51.348s
user    0m40.623s
sys     0m8.666s
"""
    outdir = "converted"
    for i in glob.glob("wheels/*.whl"):
        infile = Path(i)
        outfile = Path(outdir).joinpath(infile.name)
        wgc2.recompress(i, outfile)

else:
    """
real    1m24.037s
user    1m21.935s
sys     0m1.851s
"""
    outdir = "rewritten"
    for i in glob.glob("wheels/*.whl"):
        infile = Path(i)
        outfile = Path(outdir).joinpath(infile.name)
        wgc2.rewrite(i, outfile)

"""
$ du -hs converted/ rewritten/
448M    converted/
543M    rewritten/
"""
