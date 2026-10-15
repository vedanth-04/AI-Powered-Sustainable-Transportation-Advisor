"""Selective Remote ZIP Byte-Range Extractor for Delhi Bus GPS Dataset.

Retrieves a single daily SQLite database (2019-07-01.db) from the Zenodo
July 2019 archive (july_19_corrected.zip) using HTTP Range requests without
downloading the full 1.8 GB archive.
"""

from __future__ import annotations

import os
import sqlite3
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path

# URL and target metadata for the July 2019 Delhi Bus GPS Archive on Zenodo
ZENODO_ARCHIVE_URL = (
    "https://zenodo.org/records/21738157/files/july_19_corrected.zip?download=1"
)
TARGET_MEMBER_NAME = "july_19_corrected/2019-07-01.db"
OUTPUT_DB_NAME = "2019-07-01.db"

# Verified central directory metadata from Zenodo archive inspection
DATA_PAYLOAD_START = 1689923027
COMPRESSED_SIZE = 61911123  # ~59.04 MB
DATA_PAYLOAD_END = DATA_PAYLOAD_START + COMPRESSED_SIZE - 1  # 1751834149
EXPECTED_UNCOMPRESSED_SIZE = 193421312  # ~184.46 MB
EXPECTED_CRC32 = 0xDD4201C1


def download_and_extract_sample(
    output_dir: Path | None = None,
    chunk_size: int = 1024 * 1024,  # 1 MB chunk
) -> Path:
    """Stream and decompress 2019-07-01.db using an HTTP byte-range request."""
    if output_dir is None:
        project_root = Path(__file__).resolve().parent.parent.parent
        output_dir = project_root / "data" / "raw"

    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / OUTPUT_DB_NAME
    tmp_path = output_dir / f"{OUTPUT_DB_NAME}.tmp"

    if target_path.exists() and target_path.stat().st_size == EXPECTED_UNCOMPRESSED_SIZE:
        print(f"[{OUTPUT_DB_NAME}] already exists and is fully verified.")
        return target_path

    print("=" * 70)
    print("Selective Byte-Range Sample Retrieval")
    print(f"Source URL       : {ZENODO_ARCHIVE_URL}")
    print(f"Target Member    : {TARGET_MEMBER_NAME}")
    print(f"Output Path      : {target_path}")
    print(f"Compressed Bytes : {COMPRESSED_SIZE:,} (~{COMPRESSED_SIZE / (1024*1024):.2f} MB)")
    print(f"Uncompressed Exp : {EXPECTED_UNCOMPRESSED_SIZE:,} (~{EXPECTED_UNCOMPRESSED_SIZE / (1024*1024):.2f} MB)")
    print(f"Byte Range       : {DATA_PAYLOAD_START} to {DATA_PAYLOAD_END}")
    print("=" * 70)

    req = urllib.request.Request(
        ZENODO_ARCHIVE_URL,
        headers={"Range": f"bytes={DATA_PAYLOAD_START}-{DATA_PAYLOAD_END}"},
    )

    decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    computed_crc = 0
    total_uncompressed = 0
    total_downloaded = 0
    start_time = time.time()

    try:
        with urllib.request.urlopen(req) as response:
            if response.status not in (200, 206):
                raise RuntimeError(f"Server returned unexpected HTTP status {response.status}")

            with open(tmp_path, "wb") as out_f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    total_downloaded += len(chunk)

                    decompressed = decompressor.decompress(chunk)
                    if decompressed:
                        out_f.write(decompressed)
                        computed_crc = zlib.crc32(decompressed, computed_crc)
                        total_uncompressed += len(decompressed)

                    # Progress reporting
                    pct = (total_downloaded / COMPRESSED_SIZE) * 100
                    elapsed = max(time.time() - start_time, 0.001)
                    speed_mbps = (total_downloaded / (1024 * 1024)) / elapsed
                    sys.stdout.write(
                        f"\rDownloading: {pct:5.1f}% | "
                        f"Fetched: {total_downloaded / (1024*1024):5.1f} MB | "
                        f"Speed: {speed_mbps:4.1f} MB/s | "
                        f"Uncompressed: {total_uncompressed / (1024*1024):5.1f} MB"
                    )
                    sys.stdout.flush()

                # Flush any remaining decompressed data
                tail = decompressor.flush()
                if tail:
                    out_f.write(tail)
                    computed_crc = zlib.crc32(tail, computed_crc)
                    total_uncompressed += len(tail)

        print("\n\nDownload and decompression complete.")
        print(f"Total downloaded bytes   : {total_downloaded:,}")
        print(f"Total uncompressed bytes : {total_uncompressed:,}")
        print(f"Computed CRC32           : {hex(computed_crc)}")
        print(f"Expected CRC32           : {hex(EXPECTED_CRC32)}")

        if computed_crc != EXPECTED_CRC32:
            raise ValueError(
                f"CRC32 mismatch! Computed {hex(computed_crc)} != Expected {hex(EXPECTED_CRC32)}"
            )

        if total_uncompressed != EXPECTED_UNCOMPRESSED_SIZE:
            raise ValueError(
                f"Size mismatch! Got {total_uncompressed} bytes, expected {EXPECTED_UNCOMPRESSED_SIZE}"
            )

        # Atomic rename
        if target_path.exists():
            target_path.unlink()
        tmp_path.rename(target_path)
        print(f"Successfully saved and verified: {target_path}")

        # SQLite integrity verification
        print("\nRunning SQLite integrity verification...")
        with sqlite3.connect(f"{target_path.as_uri()}?mode=ro", uri=True) as conn:
            cursor = conn.cursor()
            status = cursor.execute("PRAGMA integrity_check;").fetchone()[0]
            print(f"PRAGMA integrity_check   : {status}")
            row_count = cursor.execute("SELECT COUNT(*) FROM vehicle_feed;").fetchone()[0]
            print(f"Total rows in vehicle_feed: {row_count:,}")

        return target_path

    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Selective extraction failed: {exc}") from exc


if __name__ == "__main__":
    download_and_extract_sample()
