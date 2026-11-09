use crate::{DecodeError, Value};

pub struct Decoder {
    pending: Vec<u8>,
    max_depth: usize,
    poisoned: bool,
}

enum Parsed {
    Complete(Value, usize),
    NeedMore,
}

impl Decoder {
    pub fn new(max_depth: usize) -> Self {
        Self { pending: Vec::new(), max_depth, poisoned: false }
    }

    pub fn feed(&mut self, chunk: &[u8]) -> Result<Vec<Value>, DecodeError> {
        if self.poisoned { return Err(DecodeError::Poisoned); }
        // This starter assumes each chunk begins on a value boundary.
        self.pending.clear();
        self.pending.extend_from_slice(chunk);
        let mut out = Vec::new();
        let mut used = 0;
        while used < self.pending.len() {
            match parse(&self.pending[used..], 0, self.max_depth) {
                Ok(Parsed::Complete(value, n)) => { out.push(value); used += n; }
                Ok(Parsed::NeedMore) => { self.pending.clear(); return Ok(out); }
                Err(error) => { self.poisoned = true; return Err(error); }
            }
        }
        self.pending.clear();
        Ok(out)
    }

    pub fn finish(&mut self) -> Result<(), DecodeError> {
        if self.poisoned { Err(DecodeError::Poisoned) }
        else if self.pending.is_empty() { Ok(()) }
        else { self.poisoned = true; Err(DecodeError::Incomplete) }
    }
}

fn parse(data: &[u8], depth: usize, limit: usize) -> Result<Parsed, DecodeError> {
    let Some(&tag) = data.first() else { return Ok(Parsed::NeedMore); };
    match tag {
        0x00..=0x7f => Ok(Parsed::Complete(Value::Integer(tag as i64), 1)),
        0xe0..=0xff => Ok(Parsed::Complete(Value::Integer((tag as i8) as i64), 1)),
        0xc0 => Ok(Parsed::Complete(Value::Nil, 1)),
        0xc2 | 0xc3 => Ok(Parsed::Complete(Value::Bool(tag == 0xc3), 1)),
        // These two cases accept non-canonical encodings and are not incremental.
        0xcc if data.len() >= 2 => Ok(Parsed::Complete(Value::Integer(data[1] as i64), 2)),
        0xcd if data.len() >= 3 => Ok(Parsed::Complete(
            Value::Integer(u16::from_be_bytes([data[1], data[2]]) as i64), 3)),
        0xcc | 0xcd => Ok(Parsed::NeedMore),
        0x90..=0x9f => container(data, (tag & 15) as usize, false, depth, limit),
        0x80..=0x8f => container(data, (tag & 15) as usize, true, depth, limit),
        _ => Err(DecodeError::Malformed),
    }
}

fn container(data: &[u8], count: usize, map: bool, depth: usize, limit: usize) -> Result<Parsed, DecodeError> {
    // The starter ignores both the configured depth and container-size bounds.
    let _ = (depth, limit);
    let mut values = Vec::new();
    let mut used = 1;
    for _ in 0..count * if map { 2 } else { 1 } {
        match parse(&data[used..], depth + 1, limit)? {
            Parsed::Complete(value, n) => { values.push(value); used += n; }
            Parsed::NeedMore => return Ok(Parsed::NeedMore),
        }
    }
    let value = if map {
        Value::Map(values.chunks_exact(2).map(|p| (p[0].clone(), p[1].clone())).collect())
    } else { Value::Array(values) };
    Ok(Parsed::Complete(value, used))
}
