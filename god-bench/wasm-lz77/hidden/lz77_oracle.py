"""Independent strict decoder for the LZ77-T1 wire format."""

MAX_DISTANCE = 32768
MAX_OUTPUT_BYTES = 32 * 1024 * 1024


def decode(stream: bytes, *, max_output: int = MAX_OUTPUT_BYTES) -> bytes:
    output = bytearray()
    position = 0

    while position < len(stream):
        control = stream[position]
        position += 1

        if control < 0x80:
            length = control + 1
            end = position + length
            if end > len(stream):
                raise ValueError("truncated literal token")
            if len(output) + length > max_output:
                raise ValueError("decoded output exceeds limit")
            output.extend(stream[position:end])
            position = end
            continue

        length = (control & 0x7F) + 3
        if position + 2 > len(stream):
            raise ValueError("truncated back-reference token")
        distance = int.from_bytes(stream[position:position + 2], "little") + 1
        position += 2
        if distance > MAX_DISTANCE:
            raise ValueError("back-reference exceeds 32 KiB window")
        if distance > len(output):
            raise ValueError("back-reference precedes output")
        if len(output) + length > max_output:
            raise ValueError("decoded output exceeds limit")
        for _ in range(length):
            output.append(output[-distance])

    return bytes(output)


def encode_literals(data: bytes) -> bytes:
    """Create a valid stream without sharing candidate encoder logic."""
    encoded = bytearray()
    for start in range(0, len(data), 128):
        piece = data[start:start + 128]
        encoded.append(len(piece) - 1)
        encoded.extend(piece)
    return bytes(encoded)


def backreference(length: int, distance: int) -> bytes:
    if not 3 <= length <= 130:
        raise ValueError("invalid match length")
    if not 1 <= distance <= 65536:
        raise ValueError("distance cannot be represented")
    return bytes([0x80 | (length - 3)]) + (distance - 1).to_bytes(2, "little")
