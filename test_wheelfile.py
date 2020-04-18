"""
Tests for layered wheel implementation.
"""

import timeit

from wheelfile import *


def extractall():
    with open_wheel() as w:
        for member in w.filelist:
            w.open(member).read()


def test_extracttime():
    print(
        "extract time: {:.2f}".format(
            timeit.timeit(
                "extractall()",
                setup="gc.enable(); from test_wheelfile import extractall",
                number=1,
            )
        )
    )


def test_wheelfile():
    w = open_wheel()
    rr = recordReader(w.read(f"{w.dist_info}/RECORD").decode("utf-8").splitlines())
    pprint.pprint(len(list(rr)))


def test_rfc822():
    """
    Test the key: value parsers.
    """
    wa = WheelArchiver("tensorflow-2.1.0-cp37-cp37m-manylinux2010_x86_64.whl")
    md = parse_kv(wa.open(wa.wheelfile_path))
    wf = parse_kv(wa.open(wa.metadata_path))

    print(write_kv(md).decode("utf-8"))
    print(write_kv(wf).decode("utf-8"))


def open_wheel():
    """
    Open an interesting wheel.
    """
    w = WheelArchiver(
        "tensorflow-2.1.0-cp37-cp37m-manylinux2010_x86_64.whl",
        "r",
        namever="tensorflow-2.1.0",
    )
    return w
