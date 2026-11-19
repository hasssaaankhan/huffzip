<div align="center">

# 🗜️ HuffZip

### Small files. Smart bits. Zero data loss.

**A complete, dependency-free file compression project built with Python and Huffman Coding.**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Dependencies](https://img.shields.io/badge/Dependencies-None-16a34a)](#-requirements)
[![Algorithm](https://img.shields.io/badge/Algorithm-Huffman%20Coding-7c3aed)](#-how-it-works)

</div>

---

## ✨ What is HuffZip?

HuffZip is a command-line file compressor that implements **Huffman Coding**, a classic greedy algorithm from data structures and algorithms (DSA).

It reads any file as bytes, counts how often each byte occurs, builds a binary Huffman tree, and represents frequent bytes with shorter bit patterns. It can then reconstruct the exact original file.

> **Lossless means exact:** decompressing an archive reproduces every original byte—not an approximation.

### At a glance

| Capability | Details |
|---|---|
| Algorithm | Greedy Huffman coding with a min-heap |
| Input | Any file: text, images, PDFs, archives, and binary data |
| Output | Versioned `.huff` archive |
| Integrity | CRC-32 verification |
| Memory | Bounded chunk-based file I/O |
| Dependencies | Python standard library only |
| Interface | Simple command-line interface |

## 🚀 Quick start

### 1. Requirements

- Python **3.10 or newer**
- No pip installs and no third-party packages

Check Python:

```bash
python --version
```

### 2. Get the project

```bash
git clone https://github.com/YOUR-USERNAME/huffzip.git
cd huffzip
```

Or download the three project files into one folder:

```text
huffzip/
├── huffzip.py
├── test_huffzip.py
└── README.md
```

### 3. Compress a file

```bash
python huffzip.py compress report.pdf
```

Creates `report.pdf.huff` in the same folder.

Choose a custom destination:

```bash
python huffzip.py compress report.pdf -o backup.huff
```

### 4. Decompress it

```bash
python huffzip.py decompress report.pdf.huff
```

Creates `report.pdf` (the `.huff` suffix is removed).

Choose a custom destination:

```bash
python huffzip.py decompress backup.huff -o recovered.pdf
```

### 5. Run the test suite

```bash
python -m unittest -v
```

The tests cover empty files, repeated bytes, all 256 byte values, text and binary round trips, malformed archives, corruption, and path safety.

---

## 🧭 Command reference

```text
python huffzip.py compress INPUT [-o OUTPUT] [--force]
python huffzip.py decompress INPUT [-o OUTPUT] [--force]
```

| Option | Meaning |
|---|---|
| `compress` | Encode a file into a `.huff` archive |
| `decompress` | Restore a file from a `.huff` archive |
| `-o`, `--output` | Set the output path |
| `--force` | Allow replacing an existing output file |
| `-h`, `--help` | Show command help |

**Safety by default:** HuffZip refuses to overwrite an existing output. Add `--force` only when you intentionally want to replace it. Input and output paths must be different.

---

## 🧠 How the algorithm works

Huffman coding is a greedy compression algorithm. It gives shorter codes to more frequent symbols and longer codes to less frequent symbols.

1. **Frequency counting** — Read the file and count the occurrences of each possible byte (0–255).
2. **Build leaf nodes** — Put each byte with a non-zero frequency into a min-priority queue.
3. **Build the tree** — Repeatedly remove the two least-frequent nodes and join them under a new parent node.
4. **Generate codes** — Label left edges `0` and right edges `1`. Each root-to-leaf path becomes a byte's code.
5. **Encode** — Replace each source byte with its Huffman code and pack the bits into bytes.
6. **Decode** — Walk the same tree one bit at a time. Whenever a leaf is reached, write that byte.

### Tiny example

Suppose a file contains:

```text
AAAAABBC
```

`A` appears most often, so it receives a shorter code than `C`. The exact codes depend on deterministic tie-breaking, but the principle is:

```text
Frequent byte   → fewer bits
Rare byte       → more bits
```

The output is not guaranteed to be smaller for every input. Random or already-compressed files may grow because the archive also needs metadata. HuffZip prioritizes correctness and transparent algorithm implementation over promising a compression ratio.

## 🏗️ Project architecture

```text
                 ┌──────────────────┐
                 │     Input file   │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ Frequency + CRC  │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ Min-heap / Tree  │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │   Bit encoder    │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │    .huff file    │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ Tree bit decoder │
                 └────────┬─────────┘
                          │
                 ┌────────▼─────────┐
                 │ Exact original   │
                 └──────────────────┘
```

### Files

| File | Responsibility |
|---|---|
| `huffzip.py` | Huffman tree, bit encoding/decoding, archive format, CLI |
| `test_huffzip.py` | Automated unit and round-trip tests |
| `README.md` | Setup, usage, algorithm explanation, and project notes |

## 📦 Archive format

HuffZip uses a compact, versioned binary format. It does not use `pickle` or execute archive content.

| Field | Size | Purpose |
|---|---:|---|
| Signature | 4 bytes | Identifies a HuffZip archive (`HUFZ`) |
| Version | 1 byte | Format version (`1`) |
| Original size | 8 bytes | Expected decoded byte count |
| Encoded bit count | 8 bytes | Exact number of meaningful payload bits |
| CRC-32 | 4 bytes | Detects accidental content corruption |
| Frequency table | 2,048 bytes | 256 unsigned 64-bit byte frequencies |
| Payload | Variable | Huffman-coded bits, most-significant bit first |

The fixed header is **2,073 bytes**. The decoder rebuilds the same deterministic tree from the frequency table. The bit count distinguishes meaningful bits from final-byte padding.

### Edge cases handled

- Empty files (valid archive with an empty payload)
- A file containing only one unique byte
- All 256 possible byte values
- Non-UTF-8 and arbitrary binary data
- Truncated headers and inconsistent payload lengths
- Invalid Huffman paths and incorrect decoded sizes
- CRC mismatches and non-zero padding bits

## ⚙️ Complexity analysis (DSA)

Let:

- `n` = number of bytes in the input file
- `k` = number of distinct byte values, where `k ≤ 256`

| Operation | Time complexity | Extra space |
|---|---:|---:|
| Frequency counting | `O(n)` | `O(1)` for fixed byte alphabet |
| Build Huffman tree | `O(k log k)` | `O(k)` |
| Generate codes | `O(k)` | `O(k)` |
| Encode | `O(n × L)` bit work | `O(1)` streaming buffer |
| Decode | `O(encoded bits)` | `O(1)` tree traversal |
| Overall | `O(n × L + k log k)` | `O(k)` plus bounded I/O |

`L` is the maximum Huffman code length. Since the alphabet is fixed at 256 byte values, the tree and code table remain small. File contents are processed in chunks; the full file is not loaded into memory.

The compressor makes two sequential passes: one to calculate frequencies and CRC-32, and one to encode. This allows it to write the archive header before the payload without holding the file in RAM.

## 🛡️ Reliability choices

- **Deterministic tree construction:** heap entries include a stable insertion sequence to resolve equal frequencies consistently.
- **Atomic output:** output is written to a temporary file beside the destination and moved into place only after success.
- **Integrity check:** CRC-32 validates decoded bytes against the archive metadata. It detects accidental corruption; it is not a cryptographic authenticity guarantee.
- **Strict validation:** archive signature, version, sizes, frequency totals, payload length, code paths, decoded length, and padding are checked.
- **No unsafe deserialization:** archive metadata is parsed with `struct`; no Python objects are loaded from untrusted files.

## 🧪 Example session

```text
$ python huffzip.py compress story.txt
✓ Compressed: story.txt → story.txt.huff
  Original:  48,000 bytes
  Archive:   19,420 bytes
  Saved:     28,580 bytes
  Size ratio: 40.5% of original

$ python huffzip.py decompress story.txt.huff
✓ Restored: story.txt.huff → story.txt
  Output: 48,000 bytes
```

*Illustrative output only. Actual sizes depend on the input file.*

## 🧰 Built with

- Python 3.10+
- `heapq` — min-priority queue for the greedy Huffman tree
- `struct` — portable binary header serialization
- `zlib` — CRC-32 integrity check
- `tempfile`, `os`, `pathlib` — safe file handling
- `unittest` — automated testing

## 🗺️ Possible future improvements

- Optional graphical user interface
- Progress reporting for very large files
- Archive metadata inspection command
- Streaming archive format that supports one-pass input
- Benchmark suite against ZIP and other compressors

## 🤝 Contributing

Issues and pull requests are welcome. Helpful contributions include additional tests, performance improvements, clearer documentation, and cross-platform testing.

1. Fork the repository.
2. Create a feature branch.
3. Add or update tests.
4. Run `python -m unittest -v`.
5. Open a pull request with a clear description.

## 📄 License

No license file is included because this deliverable is intentionally limited to three files. Before publishing publicly, add a license (for example, MIT) whose terms you are comfortable with.

---

<div align="center">

**Built to demonstrate Data Structures & Algorithms through a practical, real-world tool.**

⭐ If this project helped you learn Huffman Coding, consider starring the repository.

</div>
