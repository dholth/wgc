#!/bin/python
"""
Decompress regular and .data.zip.zst wheels to memory.
"""
import glob
import dezstd
import zipfile
import io
import shutil

from pathlib import Path


def unpack(whl):
    """
    Unpack all archive members and nested archive members.
    """
    size = 0
    with zipfile.ZipFile(whl) as zf:
        for info in zf.infolist():
            with zf.open(info) as member:
                if info.filename.endswith(".zip.zst"):
                    print(info.filename)
                    decompressor = dezstd.ZSTDPullDecompressor(member)
                    target = io.BytesIO()
                    shutil.copyfileobj(
                        decompressor, target, length=dezstd.lib.ZSTD_DStreamOutSize()
                    )
                    size += unpack(target)
                    print(".zst.zip contained", size)
                else:
                    outs = member.read()
                    size += len(outs)
    return size


for path in glob.glob("rewritten/*.whl"):
    with open(path, "rb") as whl:
        print(path, unpack(whl))

"""
nested time:
real    0m9.919s
user    0m8.227s
sys     0m1.482s

standard time:
real    0m11.104s
user    0m10.222s
sys     0m0.703s
"""
