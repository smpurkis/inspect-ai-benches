"""Generated and metamorphic verification for the incremental decoder."""

import hashlib
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

FILES = Path(os.environ.get("TASK_FILES", "/app/files"))
WORK = Path(os.environ.get("TASK_HIDDEN_WORK", "/tmp/msgpack-hidden"))
TRUSTED = ("Cargo.toml", "src/lib.rs", "src/main.rs")


def _stage():
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "src").mkdir(parents=True)
    (WORK / "tests").mkdir()
    shutil.copy2(FILES / "Cargo.toml", WORK / "Cargo.toml")
    for name in ("lib.rs", "main.rs", "decode.rs"):
        source = FILES / "src" / name
        assert source.is_file() and not source.is_symlink()
        shutil.copy2(source, WORK / "src" / name)


def _enc_int(value):
    if 0 <= value <= 127:
        return bytes([value])
    if -32 <= value < 0:
        return bytes([value & 255])
    choices = (
        (0, 255, 0xCC, 1, False),
        (0, 65535, 0xCD, 2, False),
        (0, 2**32 - 1, 0xCE, 4, False),
        (0, 2**63 - 1, 0xCF, 8, False),
        (-128, -33, 0xD0, 1, True),
        (-32768, -129, 0xD1, 2, True),
        (-(2**31), -32769, 0xD2, 4, True),
        (-(2**63), -(2**31) - 1, 0xD3, 8, True),
    )
    for low, high, marker, width, signed in choices:
        if low <= value <= high:
            return bytes([marker]) + value.to_bytes(width, "big", signed=signed)
    raise AssertionError(value)


def _rust_bytes(data):
    return "&[" + ",".join(str(x) for x in data) + "]"


def _generated_cases():
    rng = random.Random(0x5A17C0DE)
    cases = []
    boundaries = [-2**63, -2**31 - 1, -2**31, -32769, -32768, -129, -128,
                  -33, -32, -1, 0, 1, 127, 128, 255, 256, 65535, 65536,
                  2**32 - 1, 2**32, 2**63 - 1]
    for value in boundaries:
        cases.append((_enc_int(value), f"Value::Integer({value}i64)"))
    for _ in range(60):
        values = [rng.randint(-2**40, 2**40) for _ in range(rng.randint(0, 8))]
        wire = bytes([0x90 + len(values)]) + b"".join(map(_enc_int, values))
        expected = "Value::Array(vec![" + ",".join(f"Value::Integer({v}i64)" for v in values) + "])"
        cases.append((wire, expected))
    return cases


def _write_generated_test():
    cases = _generated_cases()
    rows = ",\n".join(f"({_rust_bytes(w)}, {e})" for w, e in cases)
    source = f'''use msgpack_incremental::{{DecodeError, Decoder, Value, MAX_CONTAINER_ITEMS}};

fn run(chunks: &[&[u8]], depth: usize) -> Result<Vec<Value>, DecodeError> {{
    let mut d = Decoder::new(depth);
    let mut out = Vec::new();
    for chunk in chunks {{ out.extend(d.feed(chunk)?); }}
    d.finish()?;
    Ok(out)
}}

#[test]
fn generated_every_split_and_chunk_metamorphism() {{
    let cases: Vec<(&[u8], Value)> = vec![{rows}];
    for (wire, expected) in cases {{
        let whole = run(&[wire], 12).unwrap();
        assert_eq!(whole, vec![expected.clone()]);
        for split in 0..=wire.len() {{
            assert_eq!(run(&[&wire[..split], &wire[split..]], 12).unwrap(), whole,
                       "wire={{wire:?}} split={{split}}");
        }}
        let bytes: Vec<&[u8]> = wire.iter().map(std::slice::from_ref).collect();
        assert_eq!(run(&bytes, 12).unwrap(), whole);
    }}
}}

#[test]
fn nested_container_headers_and_multiple_values() {{
    let wire = [0xdd,0,0,0,1, 0xdf,0,0,0,1, 0xdc,0,1,0xc0, 0x91,0xc3, 0x2a];
    let expected = run(&[&wire], 8).unwrap();
    assert_eq!(expected.len(), 2);
    for a in 0..=wire.len() {{ for b in a..=wire.len() {{
        assert_eq!(run(&[&wire[..a], &[], &wire[a..b], &wire[b..]], 8).unwrap(), expected);
    }} }}
}}

#[test]
fn malformed_incomplete_and_poison_state() {{
    for wire in [&[0xc1][..], &[0xca,0,0,0,0], &[0xa0], &[0xc4,0]] {{
        let mut d = Decoder::new(5);
        assert_eq!(d.feed(wire), Err(DecodeError::Malformed));
        assert_eq!(d.feed(&[]), Err(DecodeError::Poisoned));
        assert_eq!(d.finish(), Err(DecodeError::Poisoned));
    }}
    for wire in [&[0xcc][..], &[0xd2,0,0], &[0xdc,0][..], &[0x92,1][..]] {{
        let mut d = Decoder::new(5);
        assert_eq!(d.feed(wire).unwrap(), Vec::<Value>::new());
        assert_eq!(d.finish(), Err(DecodeError::Incomplete));
        assert_eq!(d.finish(), Err(DecodeError::Poisoned));
    }}
}}

#[test]
fn rejects_every_noncanonical_integer_width() {{
    let wires: &[&[u8]] = &[
        &[0xcc,0], &[0xcc,127], &[0xcd,0,128], &[0xce,0,0,1,0],
        &[0xcf,0,0,0,0,0,1,0,0], &[0xd0,0xff], &[0xd0,0xe0],
        &[0xd1,0xff,0x80], &[0xd2,0xff,0xff,0x80,0x00],
        &[0xd3,0xff,0xff,0xff,0xff,0x80,0x00,0x00,0x00],
    ];
    for wire in wires {{ assert_eq!(run(&[wire], 4), Err(DecodeError::NonCanonicalInteger), "{{wire:?}}"); }}
    assert_eq!(run(&[&[0xcf,0x80,0,0,0,0,0,0,0]], 4), Err(DecodeError::IntegerOutOfRange));
}}

#[test]
fn depth_boundaries_are_exact_and_poison() {{
    assert!(run(&[&[0xc0]], 0).is_ok());
    for depth in 1..8 {{
        let mut wire = vec![0x91; depth]; wire.push(0xc0);
        assert!(run(&[&wire], depth).is_ok());
        assert_eq!(run(&[&wire], depth.saturating_sub(1)), Err(DecodeError::DepthLimit));
    }}
}}

#[test]
fn empty_containers_have_depth_one_and_poison_at_zero() {{
    let cases: &[(&[u8], Value)] = &[
        (&[0x90], Value::Array(vec![])),
        (&[0xdc,0,0], Value::Array(vec![])),
        (&[0xdd,0,0,0,0], Value::Array(vec![])),
        (&[0x80], Value::Map(vec![])),
        (&[0xde,0,0], Value::Map(vec![])),
        (&[0xdf,0,0,0,0], Value::Map(vec![])),
    ];
    for (wire, expected) in cases {{
        assert_eq!(run(&[wire], 1).unwrap(), vec![expected.clone()]);
        let mut decoder = Decoder::new(0);
        assert_eq!(decoder.feed(wire), Err(DecodeError::DepthLimit), "{{wire:?}}");
        assert_eq!(decoder.feed(&[]), Err(DecodeError::Poisoned));
        assert_eq!(decoder.finish(), Err(DecodeError::Poisoned));
    }}
}}

#[test]
fn limits_checked_from_header_before_children() {{
    let n = MAX_CONTAINER_ITEMS as u32 + 1;
    let mut array = vec![0xdd]; array.extend(n.to_be_bytes());
    let mut map = vec![0xdf]; map.extend(n.to_be_bytes());
    assert_eq!(run(&[&array], 3), Err(DecodeError::ContainerTooLarge));
    assert_eq!(run(&[&map], 3), Err(DecodeError::ContainerTooLarge));
}}

#[test]
fn emitted_values_are_not_replayed_or_cached() {{
    let mut d = Decoder::new(3);
    assert_eq!(d.feed(&[1]).unwrap(), vec![Value::Integer(1)]);
    assert!(d.feed(&[]).unwrap().is_empty());
    assert_eq!(d.feed(&[2,3]).unwrap(), vec![Value::Integer(2), Value::Integer(3)]);
    assert!(d.feed(&[]).unwrap().is_empty());
    d.finish().unwrap();
}}
'''
    (WORK / "tests" / "generated_hidden.rs").write_text(source)


def test_hidden_generated_and_metamorphic_suite():
    _stage()
    _write_generated_test()
    result = subprocess.run(
        ["cargo", "test", "--offline", "--test", "generated_hidden"], cwd=WORK,
        text=True, capture_output=True, timeout=240,
        env={**os.environ, "CARGO_NET_OFFLINE": "true"},
    )
    assert result.returncode == 0, result.stdout[-5000:] + result.stderr[-5000:]


def test_hidden_exact_artifact_and_no_bypass_surface():
    artifact = FILES / "src" / "decode.rs"
    assert artifact.is_file() and not artifact.is_symlink()
    text = artifact.read_text()
    forbidden = ("include!", "include_bytes!", "include_str!", "Command::", "std::process", "unsafe")
    assert not any(token in text for token in forbidden)
    assert "impl Decoder" in text and "pub fn feed" in text and "pub fn finish" in text
    # Trusted source calls the module directly; only decode.rs is overlaid into the staged build.
    assert "mod decode;" in (FILES / "src" / "lib.rs").read_text()
    assert hashlib.sha256((FILES / "Cargo.toml").read_bytes()).hexdigest() == "3fc0a0fc176a3534003ac47dfeb6bfba32de3262db64fb4d9093a0e837506ad2"
