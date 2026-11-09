use msgpack_incremental::Decoder;

fn hex(s: &str) -> Result<Vec<u8>, String> {
    if s.len() % 2 != 0 { return Err("hex input has odd length".into()); }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16)
        .map_err(|_| "invalid hex".to_string())).collect()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut decoder = Decoder::new(64);
    for arg in std::env::args().skip(1) {
        for value in decoder.feed(&hex(&arg)?)? { println!("{value:?}"); }
    }
    decoder.finish()?;
    Ok(())
}
