#!/usr/bin/env python3
"""
HuffZip — lossless file compression using Huffman coding.

The .huff format stores a fixed, versioned header, byte frequencies, and a
MSB-first bitstream. Frequencies make the Huffman tree reproducible without
serializing Python objects. A CRC-32 detects accidental corruption.
"""
from __future__ import annotations

import argparse
import heapq
import os
import struct
import sys
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

MAGIC = b"HUFZ"
VERSION = 1
# magic, version, original size, encoded bit count, CRC32, 256 byte frequencies
HEADER = struct.Struct(">4sBQQI256Q")
CHUNK_SIZE = 1024 * 1024
MAX_U64 = (1 << 64) - 1


class HuffZipError(Exception):
    """Base exception for expected HuffZip failures."""


class FormatError(HuffZipError):
    """The input is not a valid or supported HuffZip archive."""


class IntegrityError(HuffZipError):
    """Decoded content does not match the archive's integrity metadata."""


@dataclass
class Node:
    frequency: int
    symbol: int | None = None
    left: "Node | None" = None
    right: "Node | None" = None


def build_tree(frequencies: list[int]) -> Node | None:
    """Build a deterministic Huffman tree from exactly 256 frequencies."""
    if len(frequencies) != 256:
        raise ValueError("Expected 256 byte frequencies.")
    heap: list[tuple[int, int, Node]] = []
    serial = 0
    for symbol, frequency in enumerate(frequencies):
        if frequency < 0:
            raise ValueError("Frequencies cannot be negative.")
        if frequency:
            node = Node(frequency, symbol)
            heapq.heappush(heap, (frequency, serial, node))
            serial += 1
    if not heap:
        return None
    while len(heap) > 1:
        f1, _, left = heapq.heappop(heap)
        f2, _, right = heapq.heappop(heap)
        parent = Node(f1 + f2, None, left, right)
        heapq.heappush(heap, (f1 + f2, serial, parent))
        serial += 1
    return heap[0][2]


def build_codes(root: Node | None) -> dict[int, tuple[int, int]]:
    """Return symbol -> (integer code, number of bits)."""
    if root is None:
        return {}
    if root.symbol is not None:
        return {root.symbol: (0, 1)}
    codes: dict[int, tuple[int, int]] = {}

    def visit(node: Node, code: int, length: int) -> None:
        if node.symbol is not None:
            codes[node.symbol] = (code, length)
            return
        assert node.left is not None and node.right is not None
        visit(node.left, code << 1, length + 1)
        visit(node.right, (code << 1) | 1, length + 1)

    visit(root, 0, 0)
    return codes


def _scan(source: BinaryIO) -> tuple[list[int], int, int]:
    """Count bytes and calculate CRC in one streaming pass."""
    frequencies = [0] * 256
    size = crc = 0
    while chunk := source.read(CHUNK_SIZE):
        size += len(chunk)
        if size > MAX_U64:
            raise HuffZipError("File is too large for the archive format.")
        crc = zlib.crc32(chunk, crc)
        for value in chunk:
            frequencies[value] += 1
    return frequencies, size, crc & 0xFFFFFFFF


def _write_bits(source: BinaryIO, target: BinaryIO,
                codes: dict[int, tuple[int, int]]) -> int:
    """Encode source bytes into an MSB-first bitstream; return bit count."""
    buffer = 0
    buffered = 0
    bit_count = 0
    while chunk := source.read(CHUNK_SIZE):
        for symbol in chunk:
            code, length = codes[symbol]
            buffer = (buffer << length) | code
            buffered += length
            bit_count += length
            while buffered >= 8:
                buffered -= 8
                target.write(bytes([(buffer >> buffered) & 0xFF]))
                buffer &= (1 << buffered) - 1 if buffered else 0
    if buffered:
        target.write(bytes([(buffer << (8 - buffered)) & 0xFF]))
    return bit_count


def _atomic_output(destination: Path):
    """Create a temporary file beside destination for safe atomic replacement."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                dir=destination.parent)
    return os.fdopen(fd, "wb"), Path(name)


def compress_file(source_path: str | Path, destination_path: str | Path) -> dict:
    """Compress a file. Returns sizes and compression ratio.

    The source is scanned twice, so memory usage is bounded regardless of
    input size. The destination is replaced only after successful completion.
    """
    source = Path(source_path)
    destination = Path(destination_path)
    if not source.is_file():
        raise HuffZipError(f"Input file does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise HuffZipError("Input and output paths must be different.")

    with source.open("rb") as stream:
        frequencies, original_size, crc = _scan(stream)
    root = build_tree(frequencies)
    codes = build_codes(root)
    bit_count = sum(frequencies[s] * codes[s][1] for s in range(256) if frequencies[s])
    if bit_count > MAX_U64:
        raise HuffZipError("Encoded stream is too large for the archive format.")

    output, temp_path = _atomic_output(destination)
    try:
        with output:
            output.write(HEADER.pack(MAGIC, VERSION, original_size, bit_count,
                                     crc, *frequencies))
            with source.open("rb") as stream:
                actual_bits = _write_bits(stream, output, codes)
            if actual_bits != bit_count:
                raise HuffZipError("Source changed while it was being compressed.")
        os.replace(temp_path, destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    archive_size = destination.stat().st_size
    return {
        "original_size": original_size,
        "archive_size": archive_size,
        "saved_bytes": original_size - archive_size,
        "ratio": (archive_size / original_size) if original_size else 0.0,
        "bits": bit_count,
    }


def decompress_file(source_path: str | Path, destination_path: str | Path) -> dict:
    """Validate and decompress an archive, then atomically publish the result."""
    source = Path(source_path)
    destination = Path(destination_path)
    if not source.is_file():
        raise HuffZipError(f"Archive does not exist: {source}")
    if source.resolve() == destination.resolve():
        raise HuffZipError("Input and output paths must be different.")

    output, temp_path = _atomic_output(destination)
    try:
        with source.open("rb") as archive, output:
            raw_header = archive.read(HEADER.size)
            if len(raw_header) != HEADER.size:
                raise FormatError("Archive header is truncated.")
            fields = HEADER.unpack(raw_header)
            magic, version, original_size, bit_count, expected_crc, *frequencies = fields
            if magic != MAGIC:
                raise FormatError("Not a HuffZip archive (bad file signature).")
            if version != VERSION:
                raise FormatError(f"Unsupported archive version: {version}.")
            if sum(frequencies) != original_size:
                raise FormatError("Frequency table does not match original size.")
            expected_payload = (bit_count + 7) // 8
            if source.stat().st_size != HEADER.size + expected_payload:
                raise FormatError("Archive payload length is inconsistent or truncated.")
            root = build_tree(list(frequencies))
            if original_size and root is None:
                raise FormatError("Missing Huffman tree.")
            if not original_size and (bit_count or any(frequencies)):
                raise FormatError("Invalid empty-file metadata.")
            if original_size and root and root.symbol is not None and bit_count != original_size:
                raise FormatError("Invalid single-symbol bit count.")
            if root is not None and root.symbol is not None:
                while chunk := archive.read(CHUNK_SIZE):
                    if any(chunk):
                        raise FormatError("Invalid non-zero bit in single-symbol payload.")
                archive.seek(HEADER.size)

            crc = 0
            written = 0
            if root is not None and root.symbol is not None:
                remaining = original_size
                block = bytes([root.symbol]) * min(CHUNK_SIZE, remaining)
                while remaining:
                    part = block[:min(len(block), remaining)]
                    output.write(part)
                    crc = zlib.crc32(part, crc)
                    written += len(part)
                    remaining -= len(part)
            elif root is not None:
                node = root
                bits_left = bit_count
                while bits_left:
                    byte = archive.read(1)
                    if not byte:
                        raise FormatError("Encoded data ended unexpectedly.")
                    value = byte[0]
                    take = min(8, bits_left)
                    for shift in range(7, 7 - take, -1):
                        node = node.right if ((value >> shift) & 1) else node.left
                        if node is None:
                            raise FormatError("Invalid Huffman code in payload.")
                        if node.symbol is not None:
                            output.write(bytes([node.symbol]))
                            crc = zlib.crc32(bytes([node.symbol]), crc)
                            written += 1
                            if written > original_size:
                                raise FormatError("Decoded data exceeds declared size.")
                            node = root
                    bits_left -= take
                if node is not root:
                    raise FormatError("Encoded stream ends in the middle of a code.")

            if written != original_size:
                raise FormatError("Decoded size does not match the header.")
            if (crc & 0xFFFFFFFF) != expected_crc:
                raise IntegrityError("CRC-32 check failed: archive is corrupted.")
            # Unused low bits in the final byte must be zero.
            if bit_count % 8 and expected_payload:
                archive.seek(-1, os.SEEK_END)
                last = archive.read(1)[0]
                mask = (1 << (8 - (bit_count % 8))) - 1
                if last & mask:
                    raise FormatError("Non-zero padding bits in final byte.")
        os.replace(temp_path, destination)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {"original_size": written, "restored_size": written}


def default_compressed_path(source: Path) -> Path:
    return source.with_name(source.name + ".huff")


def default_decompressed_path(source: Path) -> Path:
    name = source.name[:-5] if source.name.lower().endswith(".huff") else source.stem + ".restored"
    return source.with_name(name if name else "restored.bin")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="huffzip",
        description="Lossless file compression powered by Huffman coding.",
        epilog="Examples: python huffzip.py compress notes.txt  |  "
               "python huffzip.py decompress notes.txt.huff")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("compress", "decompress"):
        cmd = sub.add_parser(command)
        cmd.add_argument("input", type=Path, help="input file")
        cmd.add_argument("-o", "--output", type=Path, help="output file path")
        cmd.add_argument("--force", action="store_true",
                         help="overwrite the output file if it already exists")
    args = parser.parse_args(argv)
    source = args.input
    destination = args.output or (
        default_compressed_path(source) if args.command == "compress"
        else default_decompressed_path(source))
    if destination.exists() and not args.force:
        print(f"Error: output already exists: {destination}\nUse --force to overwrite.",
              file=sys.stderr)
        return 2
    try:
        if args.command == "compress":
            stats = compress_file(source, destination)
            print(f"✓ Compressed: {source} → {destination}")
            print(f"  Original:  {stats['original_size']:,} bytes")
            print(f"  Archive:   {stats['archive_size']:,} bytes")
            print(f"  Saved:     {stats['saved_bytes']:,} bytes")
            if stats["original_size"]:
                print(f"  Size ratio: {stats['ratio']:.1%} of original")
            else:
                print("  Size ratio: n/a (empty file)")
        else:
            stats = decompress_file(source, destination)
            print(f"✓ Restored: {source} → {destination}")
            print(f"  Output: {stats['restored_size']:,} bytes")
        return 0
    except (HuffZipError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
