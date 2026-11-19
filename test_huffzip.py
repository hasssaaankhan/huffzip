"""Automated tests for HuffZip. Run: python -m unittest -v"""
import tempfile
import unittest
from pathlib import Path

from huffzip import (
    HEADER, FormatError, IntegrityError, HuffZipError,
    build_codes, build_tree, compress_file, decompress_file,
)


class HuffmanAlgorithmTests(unittest.TestCase):
    def test_tree_and_prefix_codes(self):
        root = build_tree([5, 2] + [0] * 254)
        codes = build_codes(root)
        self.assertEqual(set(codes), {0, 1})
        self.assertEqual({length for _, length in codes.values()}, {1})

    def test_empty_tree(self):
        self.assertIsNone(build_tree([0] * 256))
        self.assertEqual(build_codes(None), {})


class FileRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def round_trip(self, data):
        original = self.folder / "input.bin"
        archive = self.folder / "input.huff"
        restored = self.folder / "restored.bin"
        original.write_bytes(data)
        compress_file(original, archive)
        decompress_file(archive, restored)
        self.assertEqual(restored.read_bytes(), data)

    def test_empty_file(self):
        self.round_trip(b"")

    def test_one_repeated_symbol(self):
        self.round_trip(b"A" * 100_000)

    def test_all_byte_values(self):
        self.round_trip(bytes(range(256)) * 20)

    def test_text_and_binary(self):
        self.round_trip(("Huffman coding — lossless compression!\n" * 1000).encode())
        self.round_trip(bytes(range(256)) * 31 + b"\x00\xff")

    def test_same_path_is_rejected(self):
        path = self.folder / "same.bin"
        path.write_bytes(b"data")
        with self.assertRaises(HuffZipError):
            compress_file(path, path)

    def test_bad_signature_is_rejected_and_no_output_left(self):
        archive = self.folder / "bad.huff"
        output = self.folder / "out.bin"
        archive.write_bytes(b"not an archive")
        with self.assertRaises(FormatError):
            decompress_file(archive, output)
        self.assertFalse(output.exists())

    def test_corruption_detected_by_crc(self):
        original = self.folder / "data.bin"
        archive = self.folder / "data.huff"
        output = self.folder / "out.bin"
        original.write_bytes(b"abcdefg" * 1000)
        compress_file(original, archive)
        raw = bytearray(archive.read_bytes())
        raw[-1] ^= 0x80
        archive.write_bytes(raw)
        with self.assertRaises((IntegrityError, FormatError)):
            decompress_file(archive, output)
        self.assertFalse(output.exists())

    def test_truncated_header(self):
        archive = self.folder / "short.huff"
        archive.write_bytes(b"HUFZ")
        with self.assertRaises(FormatError):
            decompress_file(archive, self.folder / "out")

    def test_header_size_is_stable(self):
        self.assertEqual(HEADER.size, 2073)


if __name__ == "__main__":
    unittest.main(verbosity=2)
