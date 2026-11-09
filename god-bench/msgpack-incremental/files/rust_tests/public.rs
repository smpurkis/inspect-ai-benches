use msgpack_incremental::{DecodeError, Decoder, Value};

fn decode(chunks: &[&[u8]]) -> Result<Vec<Value>, DecodeError> {
    let mut decoder = Decoder::new(8);
    let mut values = Vec::new();
    for chunk in chunks { values.extend(decoder.feed(chunk)?); }
    decoder.finish()?;
    Ok(values)
}

#[test]
fn normal_nested_value() {
    assert_eq!(decode(&[&[0x92, 0x01, 0x81, 0x02, 0xc3]]).unwrap(),
        vec![Value::Array(vec![Value::Integer(1), Value::Map(vec![(Value::Integer(2), Value::Bool(true))])])]);
}

#[test]
fn edge_header_and_integer_split_at_every_byte() {
    let wire = [0xdd, 0, 0, 0, 1, 0xd1, 0xff, 0x7f];
    let expected = vec![Value::Array(vec![Value::Integer(-129)])];
    for split in 0..=wire.len() {
        assert_eq!(decode(&[&wire[..split], &wire[split..]]).unwrap(), expected, "split {split}");
    }
}

#[test]
fn invariant_chunking_matches_whole_buffer() {
    let wire = [0x01, 0x92, 0xc0, 0xcc, 0x80, 0x80];
    let whole = decode(&[&wire]).unwrap();
    let bytes: Vec<&[u8]> = wire.iter().map(std::slice::from_ref).collect();
    assert_eq!(decode(&bytes).unwrap(), whole);
}

#[test]
fn deterministic_rerun_and_poisoning() {
    let wire = [0x91, 0xcd, 0x01, 0x00];
    assert_eq!(decode(&[&wire]).unwrap(), decode(&[&wire]).unwrap());
    let mut decoder = Decoder::new(4);
    assert_eq!(decoder.feed(&[0xc1]), Err(DecodeError::Malformed));
    assert_eq!(decoder.feed(&[1]), Err(DecodeError::Poisoned));
    assert_eq!(decoder.finish(), Err(DecodeError::Poisoned));
}
