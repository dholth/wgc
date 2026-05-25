#!/usr/bin/env python
"""
Show and decode the first FileHeader() of a zip file.
"""

import struct
import sys
from pathlib import Path

# From Python's zipfile module
structFileHeader = "<4s2B4HL2L2H"
stringFileHeader = b"PK\003\004"
sizeFileHeader = struct.calcsize(structFileHeader)

# Field indices
_FH_SIGNATURE = 0
_FH_EXTRACT_VERSION = 1
_FH_EXTRACT_SYSTEM = 2
_FH_GENERAL_PURPOSE_FLAG_BITS = 3
_FH_COMPRESSION_METHOD = 4
_FH_LAST_MOD_TIME = 5
_FH_LAST_MOD_DATE = 6
_FH_CRC = 7
_FH_COMPRESSED_SIZE = 8
_FH_UNCOMPRESSED_SIZE = 9
_FH_FILENAME_LENGTH = 10
_FH_EXTRA_FIELD_LENGTH = 11

# Compression methods
COMPRESSION_METHODS = {
    0: "STORED",
    1: "SHRUNK",
    2: "REDUCED-1",
    3: "REDUCED-2",
    4: "REDUCED-3",
    5: "REDUCED-4",
    6: "IMPLODED",
    7: "RESERVED-7",
    8: "DEFLATED",
    9: "DEFLATE64",
    10: "PKWARE_IMPLODE",
    14: "LZMA",
    18: "BZIP2",
    19: "LZMA2",
    20: "ZSTD",
    93: "XZ",
    94: "MP3",
    95: "XZ_RAW",
    97: "WAVPACK",
    98: "PPMD",
    99: "AES",
}

# Zip64 extra field header ID
_ZIP64_EXTRA_FIELD_ID = 1


def decode_extra_field(extra_data):
    """Decode extra field data and return a dict of field info."""
    fields = {}
    offset = 0

    while offset < len(extra_data):
        if offset + 4 > len(extra_data):
            break

        header_id, data_size = struct.unpack("<HH", extra_data[offset : offset + 4])
        offset += 4

        if offset + data_size > len(extra_data):
            break

        field_data = extra_data[offset : offset + data_size]
        offset += data_size

        if header_id == _ZIP64_EXTRA_FIELD_ID:
            # Zip64 extended information extra field
            # Format: uncompressed_size(Q) compressed_size(Q) [relative_header_offset(Q)] [disk_start(L)]
            # The actual format depends on what's in the main header (0xffffffff values)
            parts = []
            pos = 0
            if len(field_data) >= 8:
                uncompressed = struct.unpack("<Q", field_data[pos : pos + 8])[0]
                parts.append(f"Zip64 Uncompressed size: {uncompressed}")
                pos += 8
            if len(field_data) >= 16:
                compressed = struct.unpack("<Q", field_data[pos : pos + 8])[0]
                parts.append(f"Zip64 Compressed size: {compressed}")
                pos += 8
            if len(field_data) >= 24:
                rel_header = struct.unpack("<Q", field_data[pos : pos + 8])[0]
                parts.append(f"Zip64 Relative header offset: {rel_header}")
                pos += 8
            if len(field_data) >= 28:
                disk_start = struct.unpack("<L", field_data[pos : pos + 4])[0]
                parts.append(f"Zip64 Disk start: {disk_start}")

            fields["Zip64"] = parts
        else:
            # Unknown extra field, just show hex
            fields[f"Extra field {header_id:04x}"] = field_data.hex()

    return fields


def show_fileheader(zip_path):
    """Read and display the first FileHeader from a zip file."""
    zip_path = Path(zip_path)

    with open(zip_path, "rb") as f:
        # Read the fixed 30-byte header
        header_data = f.read(sizeFileHeader)
        if len(header_data) < sizeFileHeader:
            print(f"Error: File too small (only {len(header_data)} bytes)")
            return

        # Unpack the header
        header = struct.unpack(structFileHeader, header_data)

        # Verify signature
        if header[_FH_SIGNATURE] != stringFileHeader:
            print(
                f"Error: Invalid signature {header[_FH_SIGNATURE]!r}, expected {stringFileHeader!r}"
            )
            return

        # Read filename and extra field
        filename_len = header[_FH_FILENAME_LENGTH]
        extra_len = header[_FH_EXTRA_FIELD_LENGTH]

        filename = f.read(filename_len).decode("utf-8", errors="replace")
        extra = f.read(extra_len)  # for zip64, extra contains the true file length etc.

        # It is possible for the local header to omit the compressed,
        # uncompressed size if a flag is set.

        # _MASK_USE_DATA_DESCRIPTOR: If set, crc-32, compressed size and uncompressed
        # size are zero in the local header and the real values are written in the data
        # descriptor immediately following the compressed data.

        # Parse DOS timestamp
        dos_time = header[_FH_LAST_MOD_TIME]
        dos_date = header[_FH_LAST_MOD_DATE]

        sec = (dos_time & 0x1F) * 2
        minute = (dos_time >> 5) & 0x3F
        hour = (dos_time >> 11) & 0x1F

        day = dos_date & 0x1F
        month = (dos_date >> 5) & 0x0F
        year = ((dos_date >> 9) & 0x7F) + 1980

        # Print results
        print(f"File: {zip_path}")
        print(
            f"FileHeader size: {sizeFileHeader} bytes + {filename_len} filename + {extra_len} extra"
        )
        print()
        print(f"  Signature:               {header[_FH_SIGNATURE]!r}")
        print(
            f"  Extract version:        {header[_FH_EXTRACT_VERSION]}.{header[_FH_EXTRACT_SYSTEM] >> 4}"
        )
        print(
            f"  Extract system:         {header[_FH_EXTRACT_SYSTEM] & 0x0F} (0=FAT/PKWARE, 3=UNIX)"
        )
        print(f"  General purpose bits:   {header[_FH_GENERAL_PURPOSE_FLAG_BITS]:04x}")

        compression = header[_FH_COMPRESSION_METHOD]
        print(
            f"  Compression method:     {compression} ({COMPRESSION_METHODS.get(compression, 'UNKNOWN')})"
        )

        print(f"  Last mod time:          {hour:02d}:{minute:02d}:{sec:02d}")
        print(f"  Last mod date:          {year:04d}-{month:02d}-{day:02d}")
        print(f"  CRC-32:                 {header[_FH_CRC]:08x}")
        print(f"  Uncompressed size:      {header[_FH_UNCOMPRESSED_SIZE]} bytes")
        print(f"  Compressed size:        {header[_FH_COMPRESSED_SIZE]} bytes")
        print(f"  Filename length:        {filename_len}")
        print(f"  Extra field length:     {extra_len}")
        print()
        print(f"  Filename:               {filename!r}")
        if extra:
            extra_fields = decode_extra_field(extra)
            if "Zip64" in extra_fields:
                for line in extra_fields["Zip64"]:
                    print(f"  {line}")
            for key, value in extra_fields.items():
                if key != "Zip64":
                    print(f"  {key}:            {value}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <zipfile>")
        sys.exit(1)

    show_fileheader(sys.argv[1])
