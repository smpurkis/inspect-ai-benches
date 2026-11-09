mod training_policy;

use std::{env, process};
use training_policy::{augmentation, class_weights, learning_rate, prefer_checkpoint, CheckpointMetrics};

fn parse<T: std::str::FromStr>(value: &str) -> T {
    value.parse().unwrap_or_else(|_| process::exit(2))
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let result = match args.first().map(String::as_str) {
        Some("augment") if args.len() == 4 => {
            let item = augmentation(parse(&args[1]), parse(&args[2]), parse(&args[3]));
            Ok(format!("{},{},{}", u8::from(item.flip), item.pad_x, item.pad_y))
        }
        Some("lr") if args.len() == 4 => learning_rate(parse(&args[1]), parse(&args[2]), parse(&args[3]))
            .map(|value| format!("{value:.17}")),
        Some("weights") if args.len() == 11 => {
            let mut counts = [0_u64; 10];
            for (target, value) in counts.iter_mut().zip(&args[1..]) { *target = parse(value); }
            class_weights(counts).map(|values| values.iter().map(|v| format!("{v:.17}")).collect::<Vec<_>>().join(","))
        }
        Some("checkpoint") if args.len() == 7 => {
            let candidate = CheckpointMetrics { validation_accuracy: parse(&args[1]), validation_loss: parse(&args[2]), epoch: parse(&args[3]) };
            let current = CheckpointMetrics { validation_accuracy: parse(&args[4]), validation_loss: parse(&args[5]), epoch: parse(&args[6]) };
            prefer_checkpoint(candidate, Some(current)).map(|value| value.to_string())
        }
        Some("checkpoint-none") if args.len() == 4 => {
            let candidate = CheckpointMetrics { validation_accuracy: parse(&args[1]), validation_loss: parse(&args[2]), epoch: parse(&args[3]) };
            prefer_checkpoint(candidate, None).map(|value| value.to_string())
        }
        _ => Err("usage"),
    };
    match result { Ok(output) => println!("{output}"), Err(_) => process::exit(2) }
}
