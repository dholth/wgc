#!/usr/bin/env python
import os
from pathlib import Path

import wgc2

outdir = "recompressed"
inputs = [*Path("dataset").expanduser().rglob("**/*.whl")]

if True:  # recompress them with inner tar.zst
    outdir = "recompressed_tar"
    for infile in inputs:
        outfile = Path(outdir).joinpath(infile.name)
        print(f"{infile} -> {outfile}")
        wgc2.recompress_tar(infile, outfile)
        in_size = os.path.getsize(infile)
        out_size = os.path.getsize(outfile)
        ratio = out_size / in_size * 100
        print(f"  {ratio:.1f}% ({out_size} bytes)")

elif False:  # recompress them with inner zip.zst
    """
real    0m51.348s
user    0m40.623s
sys     0m8.666s
"""
    outdir = "recompressed"
    for infile in inputs:
        outfile = Path(outdir).joinpath(infile.name)
        print(f"{infile} -> {outfile}")
        wgc2.recompress(infile, outfile)
        in_size = os.path.getsize(infile)
        out_size = os.path.getsize(outfile)
        ratio = out_size / in_size * 100
        print(f"  {ratio:.1f}% ({out_size} bytes)")

else:  # just rewrite them with whatever the wgc2 defaults are
    """
real    1m24.037s
user    1m21.935s
sys     0m1.851s
"""
    outdir = "rewritten"
    for infile in inputs:
        outfile = Path(outdir).joinpath(infile.name)
        wgc2.rewrite(i, outfile)
        in_size = os.path.getsize(infile)
        out_size = os.path.getsize(outfile)
        ratio = out_size / in_size * 100
        print(f"  {ratio:.1f}% ({out_size} bytes)")

"""
$ du -hs converted/ rewritten/
448M    converted/
543M    rewritten/
"""
