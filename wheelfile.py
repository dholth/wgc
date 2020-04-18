#!/usr/bin/env python
"""
Layered wheel implementation
"""

import base64
import csv
import hashlib
import io
import pprint
import re
import shutil
import subprocess
import zipfile

import email.policy


# Non-greedy matching of an optional build number may be too clever (more
# invalid wheel filenames will match). Separate regex for .dist-info?
WHEEL_INFO_RE = re.compile(
    r"""^(?P<namever>(?P<name>.+?)-(?P<ver>.+?))(-(?P<build>\d[^-]*))?
     -(?P<pyver>.+?)-(?P<abi>.+?)-(?P<plat>.+?)\.whl$""",
    re.VERBOSE,
)


class HashStream(io.BufferedIOBase):
    """
    Forward operations to an underlying stream, calculating a hash as we go.

    For reading *or* writing, not both.
    """

    # blake2b 11.39s vs sha256 11.75s vs passthrough 7.68s
    def __init__(self, backing: io.BufferedIOBase, callback, algo="blake2s"):
        super().__init__()
        self.backing = backing
        self.length = 0
        self.digest = hashlib.new(algo)
        self.callback = callback

    # one of these methods makess recordReader() fail
    # (we haven't written the entire io interface)

    # def closed(self):
    #     return self.backing.closed()

    # def readable(self):
    #     return self.backing.readable()

    # def writable(self):
    #     return self.backing.writable()

    def write(self, b):
        self.digest.update(b)
        self.length += len(b)
        return self.backing.write(b)

    def read(self, n=None):
        data = self.backing.read(n)
        self.digest.update(data)
        self.length += len(data)
        return data

    def close(self):
        super().close()
        self.callback(self)
        return self.backing.close()


class WheelArchiver(zipfile.ZipFile):
    """
    Open a wheel file for reading *or* writing, not both.

    Wraps ZipFile to handle {namever}/RECORD.

    Check read files against RECORD in read mode.

    Automatically write RECORD on close in write mode.

    Defer writes to dist-info until close? Or raise if non-dist-info files written after any dist-info is written.

    Args:
        namever (str):
            First part of the wheel filename, the package name and version.
            e.g. "beaglevote-1.0". Or parsed from filename if given.
    """

    def __init__(self, *args, namever=None, **kwargs):
        super().__init__(*args, **kwargs)
        if namever is None and self.filename:
            namever = WHEEL_INFO_RE.match(self.filename).group("namever")
        self.namever = namever
        self._file_hashes = {}  # if mode = 'r' initialize from RECORD
        self._file_sizes = {}

    @property
    def dist_info(self):
        return f"{self.namever}.dist-info"

    @property
    def wheelfile_path(self):
        return self.dist_info + "/WHEEL"

    @property
    def metadata_path(self):
        return self.dist_info + "/METADATA"

    @property
    def record_path(self):
        return self.dist_info + "/RECORD"

    def open(self, name, *args, **kwargs):
        """
        Buffer files written to the dist-info directory and append to wheel on close.
        """
        if isinstance(name, zipfile.ZipInfo):
            fname = name.filename
        else:
            fname = name
        return HashStream(
            super().open(name, *args, **kwargs),
            lambda hash: self._hash_callback(fname, hash),
        )

    def _hash_callback(self, fname, hashwriter: HashStream):
        self._file_hashes[fname] = (
            hashwriter.digest.name,
            urlsafe_b64encode(hashwriter.digest.digest()).decode("charmap"),
        )
        self._file_sizes[fname] = hashwriter.length


def urlsafe_b64encode(data):
    """urlsafe_b64encode without padding"""
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def urlsafe_b64decode(data):
    """urlsafe_b64decode without padding"""
    pad = b"=" * (4 - (len(data) & 3))
    return base64.urlsafe_b64decode(data + pad)


def recordWriter(data):
    return csv.writer(data, delimiter=",", quotechar='"', lineterminator="\n")


def recordReader(data):
    return csv.reader(data, delimiter=",", quotechar='"', lineterminator="\n")


policy = email.policy.EmailPolicy(utf8=True, max_line_length=0)


def parse_kv(fp):
    """
    parse bytes from fp.read() for METADATA or WHEEL.

    Overkill for just getting the wheel version.
    """
    # HashStream isn't complete enough to send to .parse()
    # This will be good for round-tripping (parse / generate), may be
    # details getting "normal" Unicode in and out, beware surrogates.
    return email.parser.BytesParser(policy=policy).parsebytes(fp.read())


def write_kv(kv):
    """
    Return bytes for an EmailMessage (representing WHEEL or METADATA)

    Overkill for WHEEL (can generate with a string template), useful
    for METADATA.

    Would be convenient to alsos accept a sequence of key-value pairs.
    [('Wheel-Version', '1.0'),
    ('Generator', 'bdist_wheel (0.31.1)'),
    ('Root-Is-Purelib', 'false'),
    ('Tag', 'cp37-cp37m-manylinux2010_x86_64')]
    """
    return kv.as_bytes(policy=policy)
