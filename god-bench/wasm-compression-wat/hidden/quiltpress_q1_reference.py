#!/usr/bin/env python3
"""
QuiltPress-Q1 reference decompressor for hidden cross-codec tests.

This is a corrected reference implementation of the QuiltPress-Q1 format.
It is used by the hidden tests to decompress data that was compressed by
the candidate WASM implementation, verifying format compatibility.

The key function exposed to tests is decompress_bytes(blob: bytes) -> bytes.
"""

import struct
from collections import Counter, defaultdict

MAGIC = b"QPX1"
VERSION = 1
METHOD_CUSTOM = 2

CHUNK_LEN = 5
DEFAULT_DICT_COUNT_BYTES = 2
MIN_DICT_COUNT_BYTES = 1
MAX_DICT_COUNT_BYTES = 4
MAX_COMPRESS_INPUT_SIZE = 32 * 1024 * 1024
MAX_ORIGINAL_SIZE = 64 * 1024 * 1024

HEADER_FMT = "<4sBBBQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def _max_dict_size(dict_count_bytes: int) -> int:
    return (1 << (8 * dict_count_bytes)) - 1


def build_dictionary(data: bytes, max_dict: int) -> list:
    if len(data) < CHUNK_LEN:
        return []
    counts = Counter(data[i : i + CHUNK_LEN] for i in range(len(data) - CHUNK_LEN))
    candidates = []
    for chunk, freq in counts.items():
        if freq < 3:
            continue
        savings = freq * (CHUNK_LEN - 1) - CHUNK_LEN
        if savings > 0:
            candidates.append((savings, freq, chunk))
    candidates.sort(reverse=True)
    return [chunk for _, _, chunk in candidates[:max_dict]]


def encode_payload(data: bytes, dictionary: list, dict_count_bytes: int) -> bytes:
    by_first = defaultdict(list)
    for idx, chunk in enumerate(dictionary):
        by_first[chunk[0]].append((idx, chunk))

    out = bytearray()
    lit_buf = bytearray()
    tok_buf = []

    def flush_literals():
        nonlocal lit_buf
        while lit_buf:
            piece = lit_buf[:255]
            del lit_buf[:255]
            out.append(0x00)
            out.append(len(piece))
            out.extend(piece)

    def flush_tokens():
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


def compress_bytes(data: bytes, dict_count_bytes: int = DEFAULT_DICT_COUNT_BYTES) -> bytes:
    _validate_dict_count_bytes(dict_count_bytes)
    if len(data) > MAX_COMPRESS_INPUT_SIZE:
        raise ValueError("compression input exceeds limit")
    max_dict = _max_dict_size(dict_count_bytes)
    dictionary = build_dictionary(data, max_dict=max_dict)
    payload = encode_payload(data, dictionary, dict_count_bytes=dict_count_bytes)
    header = struct.pack(HEADER_FMT, MAGIC, VERSION, METHOD_CUSTOM,
                         dict_count_bytes, len(data))
    blob = bytearray(header)
    blob.extend(len(dictionary).to_bytes(dict_count_bytes, "little"))
    for chunk in dictionary:
        blob.extend(chunk)
    blob.extend(payload)
    return bytes(blob)


def _validate_dict_count_bytes(dict_count_bytes: int) -> None:
    if not (MIN_DICT_COUNT_BYTES <= dict_count_bytes <= MAX_DICT_COUNT_BYTES):
        raise ValueError(
            f"dict_count_bytes must be in [{MIN_DICT_COUNT_BYTES}, {MAX_DICT_COUNT_BYTES}]"
        )


def decode_payload(
    payload: bytes,
    original_size: int,
    dictionary: list,
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
                out.extend(chunk)
            p += token_bytes

        else:
            raise ValueError(f"unknown command byte: {cmd}")

        if len(out) > original_size:
            raise ValueError("decoded output exceeds expected size")

    if len(out) != original_size:
        raise ValueError("decoded size mismatch")

    return bytes(out)


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
    if original_size > MAX_ORIGINAL_SIZE:
        raise ValueError("declared original size exceeds limit")

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
