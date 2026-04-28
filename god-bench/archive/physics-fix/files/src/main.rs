use std::fs;

use clap::Parser;

use gr_sim::types::*;
use gr_sim::{os_collapse, solve_tov};

#[derive(Parser)]
#[command(name = "gr_sim")]
#[command(about = "General-relativity stellar collapse simulator")]
struct Cli {
    /// Path to the input seed file (JSON).
    #[arg(short, long)]
    input: String,

    /// Path to the output file (JSON).  Prints to stdout if omitted.
    #[arg(short, long)]
    output: Option<String>,
}

fn main() {
    let cli = Cli::parse();

    let content = fs::read_to_string(&cli.input).unwrap_or_else(|e| {
        eprintln!("Error reading {}: {}", cli.input, e);
        std::process::exit(1);
    });

    let config: SimConfig = serde_json::from_str(&content).unwrap_or_else(|e| {
        eprintln!("Error parsing seed JSON: {}", e);
        std::process::exit(1);
    });

    let output = run_simulation(&config);

    let json_str = serde_json::to_string(&output).unwrap_or_else(|e| {
        eprintln!("Error serializing output: {}", e);
        std::process::exit(1);
    });

    match cli.output.as_deref() {
        Some(path) => fs::write(path, &json_str).unwrap_or_else(|e| {
            eprintln!("Error writing {}: {}", path, e);
            std::process::exit(1);
        }),
        None => print!("{}", json_str),
    }
}

fn run_simulation(config: &SimConfig) -> SimOutput {
    let mode = config.mode.as_str();

    let tov_result = if mode == "tov" || mode == "both" {
        let tov_cfg = config.tov.as_ref().unwrap_or_else(|| {
            eprintln!("Mode '{}' requires a 'tov' configuration block", mode);
            std::process::exit(1);
        });
        Some(solve_tov(tov_cfg))
    } else {
        None
    };

    let collapse_result = if mode == "collapse" || mode == "both" {
        let col_cfg = config.collapse.as_ref().unwrap_or_else(|| {
            eprintln!(
                "Mode '{}' requires a 'collapse' configuration block",
                mode
            );
            std::process::exit(1);
        });
        Some(os_collapse(col_cfg))
    } else {
        None
    };

    SimOutput {
        tov: tov_result,
        collapse: collapse_result,
    }
}
