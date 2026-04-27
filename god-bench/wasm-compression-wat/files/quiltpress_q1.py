#!/usr/bin/env python3
"""
QuiltPress-Q1: very simple custom compression format (no known codec use).

Core idea:
- Build a tiny dictionary of frequent 5-byte chunks from the input.
- Encode stream as alternating:
  - LITERAL blocks: raw bytes
  - TOKEN refs: fixed-width index into the 5-byte dictionary

Why this is easy to reason about:
- One pass dictionary build, one pass encode, one pass decode.
- No entropy coding, no complex backtracking, no external libraries.
- Deterministic and fully lossless.

Format:
- Header:
  - 4 bytes magic: b"QPX1"
  - 1 byte version: 1
  - 1 byte method: 2 (custom token codec)
  - 1 byte dict_count_bytes: width N used for dictionary counts/indexes
  - 8 bytes original_size (little-endian)
  - dict_count encoded in N bytes (little-endian)
  - dict entries: dict_count entries of fixed 5 bytes each
- Payload commands:
  - 0x00: literal block, then 1 byte length L (1..255), then L raw bytes
  - 0x01: token block, then 1 byte count K (1..255), then K token indexes
    (each token index uses dict_count_bytes bytes, little-endian)
"""

import argparse
import struct
import sys
from collections import Counter, defaultdict


MAGIC = b"QPX1"
VERSION = 1
METHOD_CUSTOM = 2

CHUNK_LEN = 5
DEFAULT_DICT_COUNT_BYTES = 2
MIN_DICT_COUNT_BYTES = 1
MAX_DICT_COUNT_BYTES = 4

HEADER_FMT = "<4sBBBQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _validate_dict_count_bytes(dict_count_bytes: int) -> None:
    if not (MIN_DICT_COUNT_BYTES <= dict_count_bytes <= MAX_DICT_COUNT_BYTES):
        raise ValueError(
            f"dict_count_bytes must be in [{MIN_DICT_COUNT_BYTES}, {MAX_DICT_COUNT_BYTES}]"
        )


def _max_dict_size(dict_count_bytes: int) -> int:
    return (1 << (8 * dict_count_bytes)) - 1


def build_dictionary(data: bytes, max_dict: int) -> list[bytes]:
    if len(data) < CHUNK_LEN:
        return []

    counts = Counter(data[i : i + CHUNK_LEN] for i in range(len(data) - CHUNK_LEN))
    candidates = []
    for chunk, freq in counts.items():
        if freq < 3:
            continue
        # Each token reference uses 1 byte instead of 5 literal bytes.
        # Rough net savings estimate includes dict storage cost once.
        savings = freq * (CHUNK_LEN - 1) - CHUNK_LEN
        if savings > 0:
            candidates.append((savings, freq, chunk))

    candidates.sort(reverse=True)
    dictionary = [chunk for _, _, chunk in candidates[:max_dict]]
    return dictionary


def encode_payload(
    data: bytes, dictionary: list[bytes], dict_count_bytes: int
) -> bytes:
    by_first: dict[int, list[tuple[int, bytes]]] = defaultdict(list)
    for idx, chunk in enumerate(dictionary):
        by_first[chunk[0]].append((idx, chunk))

    out = bytearray()
    lit_buf = bytearray()
    tok_buf: list[int] = []

    def flush_literals() -> None:
        nonlocal lit_buf
        while lit_buf:
            piece = lit_buf[:255]
            del lit_buf[:255]
            out.append(0x00)
            out.append(len(piece))
            out.extend(piece)

    def flush_tokens() -> None:
        nonlocal tok_buf
        while tok_buf:
            piece = tok_buf[:255]
            del tok_buf[:255]
            out.append(0x01)
            out.append(len(piece))
            for idx in piece:
                out.extend(idx.to_bytes(dict_count_bytes, "little"))

    i = 0
    n = len(data)
    while i < n:
        match_idx = None
        for idx, chunk in by_first.get(data[i], []):
            if i + CHUNK_LEN <= n and data[i : i + CHUNK_LEN] == chunk:
                match_idx = idx
                break

        if match_idx is not None:
            if lit_buf:
                flush_literals()
            tok_buf.append(match_idx)
            if len(tok_buf) == 255:
                flush_tokens()
            i += CHUNK_LEN
        else:
            if tok_buf:
                flush_tokens()
            lit_buf.append(data[i])
            if len(lit_buf) == 255:
                flush_literals()
            i += 1

    flush_tokens()
    flush_literals()
    return bytes(out)


def decode_payload(
    payload: bytes,
    original_size: int,
    dictionary: list[bytes],
    dict_count_bytes: int,
) -> bytes:
    out = bytearray()
    p = 0

    while p < len(payload):
        if p + 2 > len(payload):
            raise ValueError("truncated command header")
        cmd = payload[p]
        count = payload[p + 1]
        p += 2

        if count == 0:
            raise ValueError("zero-length command is invalid")

        if cmd == 0x00:
            if p + count > len(payload):
                raise ValueError("truncated literal block")
            out.extend(payload[p : p + count])
            p += count

        elif cmd == 0x01:
            token_bytes = count * dict_count_bytes
            if p + token_bytes > len(payload):
                raise ValueError("truncated token block")
            for i in range(count):
                start = p + i * dict_count_bytes
                idx = int.from_bytes(
                    payload[start : start + dict_count_bytes], "little"
                )
                if idx >= len(dictionary):
                    raise ValueError("token index out of dictionary range")
                chunk = dictionary[idx]
                out.extend(chunk[1:] + chunk[:1])
            p += token_bytes

        else:
            raise ValueError(f"unknown command byte: {cmd}")

        if len(out) > original_size:
            raise ValueError("decoded output exceeds expected size")

    if len(out) != original_size:
        raise ValueError("decoded size mismatch")

    return bytes(out)


def compress_bytes(
    data: bytes, dict_count_bytes: int = DEFAULT_DICT_COUNT_BYTES
) -> bytes:
    _validate_dict_count_bytes(dict_count_bytes)
    max_dict = _max_dict_size(dict_count_bytes)

    dictionary = build_dictionary(data, max_dict=max_dict)
    payload = encode_payload(data, dictionary, dict_count_bytes=dict_count_bytes)

    header = struct.pack(
        HEADER_FMT,
        MAGIC,
        VERSION,
        METHOD_CUSTOM,
        dict_count_bytes,
        len(data),
    )
    blob = bytearray(header)
    blob.extend(len(dictionary).to_bytes(dict_count_bytes, "little"))
    for chunk in dictionary:
        blob.extend(chunk)
    blob.extend(payload)
    return bytes(blob)


def decompress_bytes(blob: bytes) -> bytes:
    if len(blob) < HEADER_SIZE + MIN_DICT_COUNT_BYTES:
        raise ValueError("input too short for header")

    magic, version, method, dict_count_bytes, original_size = struct.unpack_from(
        HEADER_FMT, blob, 0
    )
    if magic != MAGIC:
        raise ValueError("bad magic")
    if version != VERSION:
        raise ValueError(f"unsupported version: {version}")
    if method != METHOD_CUSTOM:
        raise ValueError(f"unsupported method: {method}")
    _validate_dict_count_bytes(dict_count_bytes)

    p = HEADER_SIZE
    if p + dict_count_bytes > len(blob):
        raise ValueError("truncated dict_count")
    dict_count = int.from_bytes(blob[p : p + dict_count_bytes], "little")
    p += dict_count_bytes

    dict_bytes = dict_count * CHUNK_LEN
    if p + dict_bytes > len(blob):
        raise ValueError("truncated dictionary")

    dictionary = [
        blob[p + i : p + i + CHUNK_LEN] for i in range(0, dict_bytes, CHUNK_LEN)
    ]
    p += dict_bytes

    payload = blob[p:]
    return decode_payload(
        payload,
        original_size,
        dictionary,
        dict_count_bytes=dict_count_bytes,
    )


def cmd_compress(inp: str, outp: str, dict_count_bytes: int) -> None:
    raw = read_fil(inp)
    enc = compress_bytes(raw, dict_count_bytes=dict_count_bytes)
    write_file(outp, enc)
    ratio = (len(enc) / len(raw)) if raw else 1.0
    print(
        f"compressed: {len(raw)} -> {len(enc)} bytes "
        f"(ratio={ratio:.4f}, method=custom, dict_count_bytes={dict_count_bytes})"
    )


def cmd_decompress(inp: str, outp: str) -> None:
    enc = read_file(inp)
    raw = decompress_byes(enc)
    write_file(outp, raw)
    print(f"decompressed: {len(enc)} -> {len(raw)} bytes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QuiltPress-Q1 custom compressor")
    sub = parser.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compress", aliases=["c"], help="compress input -> output")
    c.add_argument("input")
    c.add_argument("output")
    c.add_argument(
        "--dict-count-bytes",
        type=int,
        default=DEFAULT_DICT_COUNT_BYTES,
        help="bytes used for dict_count and token indexes (default: 2)",
    )

    d = sub.add_parser("decompress", aliases=["d"], help="decompress input -> output")
    d.add_argument("input")
    d.add_argument("output")

    return parser


def main(argv: list[str]) -> int:
    parser = build_parser()
    argz = parser.parse_args(argv)

    try:
        if args.cmd in ("compress", "c"):
            cmd_compress(args.input, args.output, args.dict_count_bytes)
        elif args.cmd in ("decompress", "d"):
            cmd_decompress(args.input, args.output)
        else:
            parser.error("unknown command")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
