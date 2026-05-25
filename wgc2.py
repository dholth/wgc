#!/usr/bin/env python
# wgc "wheel greater compression"
# puts everything but *.dist-info/ in an interior archive
# requires wheel >= 0.34.2

import argparse
import hashlib
import io
import os
import os.path
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from zipfile import ZipFile

from compression.zstd import CompressionParameter, ZstdFile
from wheel.wheelfile import WheelFile

# from packaging.utils import parse_wheel_filename
from wheelfile import WheelArchiver, urlsafe_b64encode

compresslevel = "19"


class HW2(io.BufferedIOBase):
    """
    Forward operations to an underlying stream, calculating a sha256 hash as we go.
    """

    def __init__(self, backing, callback):
        super().__init__()
        self.backing = backing
        self.written = 0
        self.digest = hashlib.sha256()
        self.callback = callback

    def write(self, b):
        self.digest.update(b)
        self.written += len(b)
        return self.backing.write(b)

    def close(self):
        super().close()
        self.callback(self)
        return self.backing.close()


class Wheel2File(WheelArchiver):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.data_path = "{}.data".format(self.namever)

    @property
    def dist_info_path(self):
        return self.dist_info

    def data_tar(self):
        """
        Return inner tar for writing.
        """
        zip_name = self.data_path + ".tar.zst"
        zip_info = zipfile.ZipInfo(
            zip_name
        )  # default minimum zip datetime (1980, 1, 1, 00:00)
        zip_info.compress_type = zipfile.ZIP_STORED
        data_writer = self.open(zip_info, "w", force_zip64=True)
        # If wrapping an existing file object, the wrapped file will
        # not be closed when the ZstdFile is closed.
        zst_writer = ZstdFile(
            data_writer,
            "w",
            options={
                CompressionParameter.compression_level: 19,
                CompressionParameter.nb_workers: os.cpu_count() or 1,
            },
        )

        class ClosingTarFile(tarfile.TarFile):
            """Close wrapped fileobj's when closed, unlike TarFile, ZstdFile."""

            def close(self) -> None:
                super().close()
                zst_writer.close()
                data_writer.close()

        tar_writer = ClosingTarFile(None, "w", zst_writer, format=tarfile.PAX_FORMAT)
        return tar_writer

    def data_zip(self):
        """
        Return inner zip for writing.
        """
        use_zstd = True

        # the outer zip member may be stored or use standard compression
        if use_zstd:
            zip_name = self.data_path + ".zip.zst"
        else:
            zip_name = self.data_path + ".zip"
        zip_info = zipfile.ZipInfo(
            zip_name
        )  # default minimum zip datetime (1980, 1, 1, 00:00)
        zip_info.compress_type = (
            zipfile.ZIP_STORED if use_zstd else zipfile.ZIP_DEFLATED
        )
        data_writer = self.open(zip_info, "w")
        temp = tempfile.NamedTemporaryFile(delete=False)

        # the inner zip is always STORED
        complete = zipfile.ZipFile(temp.name, mode="w", compression=zipfile.ZIP_STORED)

        def closer(original):
            # zipfile doesn't close() if self._filePassed
            closed = False

            def close():
                nonlocal closed
                # Once only.
                if closed:
                    return
                closed = True
                original()
                if use_zstd:  # zstd mode
                    subprocess.call(["zstd", "-T0", f"-{compresslevel}", temp.name])
                    lines = open(temp.name + ".zst", "rb").readlines()
                    data_writer.writelines(lines)
                    os.unlink(temp.name + ".zst")
                else:  # regular zip compression
                    # use copyfileobj?
                    data_writer.write(open(temp.name, "rb").read())
                os.unlink(temp.name)
                data_writer.close()

            return close

        complete.close = closer(complete.close)
        return complete

    def hash_callback(self, fname, hashwriter: HW2):
        self._file_hashes[fname] = (
            hashwriter.digest.name,
            urlsafe_b64encode(hashwriter.digest.digest()).decode("charmap"),
        )
        self._file_sizes[fname] = hashwriter.written

    def open(self, *args, **kwargs):
        return HW2(
            ZipFile.open(self, *args, **kwargs),
            lambda hashwriter: self.hash_callback(
                hashwriter.backing._zinfo.filename, hashwriter
            ),
        )


def recompress(infile, outfile):
    with WheelFile(infile) as wheel_in, Wheel2File(outfile, "w") as wheel_out:
        dist_info = []
        record_path = wheel_out.dist_info_path + "/RECORD"
        with wheel_out.data_zip() as inner_zip:
            for info in wheel_in.infolist():
                if info.filename.startswith(wheel_out.dist_info_path):
                    dist_info.append(info)
                    continue
                with wheel_in.open(info, "r") as readable:
                    data = readable.read()
                info.compress_type = zipfile.ZIP_STORED
                with inner_zip.open(info, "w") as foo:
                    foo.write(data)
            inner_zip.close()

        for info in dist_info:
            if info.filename == record_path:
                continue
            with wheel_in.open(info, "r") as readable:
                data = readable.read()
            info.compress_type = zipfile.ZIP_DEFLATED
            with wheel_out.open(info, "w") as target:
                target.write(data)


def recompress_tar(infile, outfile):
    with WheelFile(infile) as wheel_in, Wheel2File(outfile, "w") as wheel_out:
        dist_info = []
        record_path = wheel_out.dist_info_path + "/RECORD"
        with wheel_out.data_tar() as inner_tar:
            for info in wheel_in.infolist():
                if info.filename.startswith(wheel_out.dist_info_path):
                    dist_info.append(info)
                    continue
                with wheel_in.open(info, "r") as readable:
                    data = readable.read()
                # XXX discards execute bit, file permissions
                tar_info = tarfile.TarInfo(name=info.filename)
                tar_info.size = len(data)
                inner_tar.addfile(tar_info, io.BytesIO(data))

        for info in dist_info:
            if info.filename == record_path:
                continue
            with wheel_in.open(info, "r") as readable:
                data = readable.read()
            info.compress_type = zipfile.ZIP_DEFLATED
            with wheel_out.open(info, "w") as target:
                target.write(data)


def rewrite(infile, outfile):
    """
    For timing comparison with the nested zip strategy.
    """
    with WheelFile(infile) as wheel_in, Wheel2File(outfile, "w") as wheel_out:
        dist_info = []
        record_path = wheel_out.dist_info_path + "/RECORD"

        inner_zip = wheel_out
        if True:
            for info in wheel_in.infolist():
                if info.filename.startswith(wheel_out.dist_info_path):
                    dist_info.append(info)
                    continue
                with wheel_in.open(info, "r") as readable:
                    data = readable.read()
                info.compress_type = zipfile.ZIP_DEFLATED
                with inner_zip.open(info, "w") as foo:
                    foo.write(data)

        for info in dist_info:
            if info.filename == record_path:
                continue
            with wheel_in.open(info, "r") as readable:
                data = readable.read()
            info.compress_type = zipfile.ZIP_DEFLATED
            with wheel_out.open(info, "w") as target:
                target.write(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("infile", nargs=1)
    parser.add_argument("outdir", nargs=1)

    parsed = parser.parse_args()

    infile = Path(parsed.infile[0])
    outdir = Path(parsed.outdir[0])

    base = infile.name
    outfile = outdir.joinpath(base)

    print(infile, outfile)

    assert not outfile.exists()

    recompress(infile, outfile)

    print(f"{base} {os.path.getsize(outfile) / os.path.getsize(infile)}")
