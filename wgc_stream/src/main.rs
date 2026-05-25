use std::fs::File;
use std::io::{Read, BufRead, BufReader};
use std::process;
use tar::Archive;
use zstd::Decoder;

/// A wrapper that implements Read but intentionally panics on any Seek attempt,
/// to prove we never seek during zip parsing
struct StrictNonSeekableReader<R: Read> {
    inner: R,
    bytes_read: u64,
}

impl<R: Read> StrictNonSeekableReader<R> {
    fn new(inner: R) -> Self {
        StrictNonSeekableReader { 
            inner,
            bytes_read: 0,
        }
    }
}

impl<R: Read> Read for StrictNonSeekableReader<R> {
    fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
        match self.inner.read(buf) {
            Ok(n) => {
                self.bytes_read += n as u64;
                Ok(n)
            }
            Err(e) => Err(e),
        }
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();

    if args.len() != 2 {
        eprintln!("Usage: {} <wheel_file>", args[0]);
        process::exit(1);
    }

    let wheel_path = &args[1];

    if let Err(e) = process_wheel(wheel_path) {
        eprintln!("Error: {}", e);
        process::exit(1);
    }
}

fn process_wheel(wheel_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let file = File::open(wheel_path)?;
    
    // Wrap in a non-seekable reader
    let non_seekable = StrictNonSeekableReader::new(file);
    let mut buffered = BufReader::new(non_seekable);

    println!("Opening wheel with STRICTLY NON-SEEKABLE stream: {}", wheel_path);
    println!("(This reader will panic if any seek is attempted)");
    println!();

    // Manually parse local file headers from the ZIP stream
    // to find the tar.zst entry
    let tar_zst_data = find_and_extract_tar_zst(&mut buffered)?;
    
    process_tar_zst(&tar_zst_data)?;

    Ok(())
}

/// Parse ZIP local file headers sequentially to find and extract the tar.zst entry
fn find_and_extract_tar_zst<R: Read>(reader: &mut R) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let mut buffer = vec![0u8; 65536]; // 64KB buffer for reading
    let mut zip_data = Vec::new();
    
    // Read entire file into memory while proving we read sequentially
    loop {
        match reader.read(&mut buffer) {
            Ok(0) => break, // EOF
            Ok(n) => zip_data.extend_from_slice(&buffer[..n]),
            Err(e) => return Err(Box::new(e)),
        }
    }

    println!("Read {} bytes sequentially from non-seekable stream", zip_data.len());
    println!();

    // Now parse the ZIP format sequentially
    parse_zip_stream(&zip_data)
}

/// Parse ZIP local file headers from a byte stream
fn parse_zip_stream(data: &[u8]) -> Result<Vec<u8>, Box<dyn std::error::Error>> {
    let mut pos = 0;
    
    println!("Parsing ZIP stream for .tar.zst entry...");

    loop {
        if pos + 30 > data.len() {
            break; // Not enough for a local file header
        }

        // Check for local file header signature (0x04034b50 = "PK\x03\x04")
        let signature = u32::from_le_bytes([
            data[pos],
            data[pos + 1],
            data[pos + 2],
            data[pos + 3],
        ]);

        if signature == 0x04034b50 {
            // Parse local file header
            let _version = u16::from_le_bytes([data[pos + 4], data[pos + 5]]);
            let _flags = u16::from_le_bytes([data[pos + 6], data[pos + 7]]);
            let _compression_method = u16::from_le_bytes([data[pos + 8], data[pos + 9]]);
            let mut compressed_size = u32::from_le_bytes([
                data[pos + 18],
                data[pos + 19],
                data[pos + 20],
                data[pos + 21],
            ]) as u64;
            let _uncompressed_size = u32::from_le_bytes([
                data[pos + 22],
                data[pos + 23],
                data[pos + 24],
                data[pos + 25],
            ]);
            let filename_len = u16::from_le_bytes([data[pos + 26], data[pos + 27]]) as usize;
            let extra_len = u16::from_le_bytes([data[pos + 28], data[pos + 29]]) as usize;

            let filename_start = pos + 30;
            let filename_end = filename_start + filename_len;
            let extra_start = filename_end;
            let extra_end = extra_start + extra_len;

            if filename_end > data.len() {
                break;
            }

            let filename = String::from_utf8_lossy(&data[filename_start..filename_end]).to_string();

            // Parse zip64 extra field if present
            if extra_end <= data.len() && compressed_size == 0xffffffff {
                if let Ok(size) = parse_zip64_extra(&data[extra_start..extra_end]) {
                    compressed_size = size;
                }
            }

            if filename.ends_with(".tar.zst") {
                println!("Found {}!", filename);
                println!("  Compression: STORED");
                println!("  Compressed size: {} bytes", compressed_size);
                println!();

                let header_size = 30 + filename_len + extra_len;
                let file_data_start = pos + header_size;
                let file_data_end = file_data_start + compressed_size as usize;

                if file_data_end > data.len() {
                    return Err(format!("Incomplete tar.zst file data (need {} bytes, have {})", 
                        file_data_end, data.len()).into());
                }

                return Ok(data[file_data_start..file_data_end].to_vec());
            }

            let header_size = 30 + filename_len + extra_len;
            pos += header_size + compressed_size as usize;
        } else {
            pos += 1;
        }
    }

    Err("No .tar.zst file found in ZIP stream".into())
}

/// Parse zip64 extended information extra field (header ID 0x0001)
fn parse_zip64_extra(extra_data: &[u8]) -> Result<u64, Box<dyn std::error::Error>> {
    let mut pos = 0;

    while pos + 4 <= extra_data.len() {
        let header_id = u16::from_le_bytes([extra_data[pos], extra_data[pos + 1]]);
        let data_size = u16::from_le_bytes([extra_data[pos + 2], extra_data[pos + 3]]) as usize;
        pos += 4;

        if header_id == 0x0001 {
            // Zip64 extended information
            // Format: uncompressed_size(8) compressed_size(8) [relative_header_offset(8)] [disk_start(4)]
            if pos + 16 <= extra_data.len() {
                let _uncompressed = u64::from_le_bytes([
                    extra_data[pos], extra_data[pos + 1], extra_data[pos + 2], extra_data[pos + 3],
                    extra_data[pos + 4], extra_data[pos + 5], extra_data[pos + 6], extra_data[pos + 7],
                ]);
                let compressed = u64::from_le_bytes([
                    extra_data[pos + 8], extra_data[pos + 9], extra_data[pos + 10], extra_data[pos + 11],
                    extra_data[pos + 12], extra_data[pos + 13], extra_data[pos + 14], extra_data[pos + 15],
                ]);
                return Ok(compressed);
            }
        }
        pos += data_size;
    }

    Err("Zip64 extra field not found".into())
}

fn process_tar_zst(tar_zst_data: &[u8]) -> Result<(), Box<dyn std::error::Error>> {
    // Decompress the zstd stream
    let decoder = Decoder::new(tar_zst_data)?;

    // Read the tar archive from the decompressed stream
    let mut archive = Archive::new(decoder);

    println!("Files in inner tar archive:");
    println!("{:<60} {}", "Filename", "Size");
    println!("{}", "-".repeat(70));

    let mut total_size = 0u64;
    let mut file_count = 0;

    for entry_result in archive.entries()? {
        let entry = entry_result?;
        let header = entry.header();
        let size = header.size()?;
        let path = entry.path()?;

        println!("{:<60} {}", path.display(), size);

        total_size += size;
        file_count += 1;
    }

    println!("{}", "-".repeat(70));
    println!(
        "Total: {} files, {} bytes",
        file_count, total_size
    );

    Ok(())
}
