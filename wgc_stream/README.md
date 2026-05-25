# wgc_stream

A Rust utility that demonstrates **streaming access to wheel files without seeking**, using the tar.zst compression strategy.

## Purpose

This program proves that wheels created by `wgc2.py`'s `recompress_tar()` function can be opened and read **without any seek operations**. This is a key advantage over traditional ZIP-based wheels:

- **Traditional ZIP wheels**: Require seeking to the end of the file to read the Central Directory. This means you can't stream a wheel over HTTP without downloading the entire file.
- **tar.zst wheels**: Can be read sequentially from the start. The stream format allows reading all files with only forward reads.

## How It Works

The program:
1. Reads the entire wheel file **sequentially** (no seeking)
2. Manually parses ZIP local file headers to find the `.tar.zst` entry
3. Handles **zip64 extended information** extra fields for large files
4. Extracts the tar.zst data
5. Decompresses with zstd and parses tar entries
6. Prints all filenames and sizes

The reader is wrapped in a `StrictNonSeekableReader` that would panic if any seek operation were attempted, proving the stream is truly non-seekable.

## Usage

```bash
cargo build --release
./target/release/wgc_stream <wheel_file>
```

Example:

```bash
./target/release/wgc_stream ../recompressed_tar/coverage-7.6.1-cp314-cp314-linux_x86_64.whl
```

## Output

```
Opening wheel with STRICTLY NON-SEEKABLE stream: ../recompressed_tar/coverage-7.6.1-cp314-cp314-linux_x86_64.whl
(This reader will panic if any seek is attempted)

Read 152580 bytes sequentially from non-seekable stream

Parsing ZIP stream for .tar.zst entry...
Found coverage-7.6.1.data.tar.zst!
  Compression: STORED
  Compressed size: 145156 bytes

Files in inner tar archive:
Filename                                                     Size
----------------------------------------------------------------------
coverage/__init__.py                                         1043
coverage/__main__.py                                          293
...
coverage/xmlreport.py                                        9775
----------------------------------------------------------------------
Total: 52 files, 662339 bytes
```

## Key Features

- ✅ **No seeking**: Proves zip64 parsing works without `Seek` trait
- ✅ **zip64 support**: Correctly parses extended information extra fields
- ✅ **Streaming format**: All data read sequentially
- ✅ **Efficient**: Demonstrates the archive can be streamed over HTTP

## Implementation Details

### Manual ZIP Parsing

Instead of using the standard `zip` crate (which requires `Seek`), this program manually parses ZIP local file headers:

```
Offset  Size  Description
------  ----  -----------
0       4     Signature (0x04034b50)
4       2     Version needed to extract
6       2     General purpose bit flag
8       2     Compression method
...
30+     N     Filename
30+N    M     Extra field
30+N+M  K     File data
```

### zip64 Extended Information

For files > 4GB, the extra field contains:
- Header ID: 0x0001
- Data size: Variable
- Uncompressed size (8 bytes)
- Compressed size (8 bytes)
- Optional: relative header offset, disk start number

## Dependencies

- `tar`: Parse tar format
- `zstd`: Decompress zstandard compression
- No external ZIP library needed (manual parsing)

## Why This Matters

This format enables:
- **Streaming installs**: Download and install while receiving data
- **Resume support**: Partial downloads work naturally
- **Reduced memory**: No need to read the entire central directory first
- **CDN-friendly**: Works with simple byte range requests

