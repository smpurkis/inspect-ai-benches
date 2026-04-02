use std::fs;

use clap::Parser;

mod sim;
mod types;

use types::*;

#[derive(Parser)]
#[command(name = "nbody_sim")]
#[command(about = "Deterministic N-body gravitational simulator")]
struct Cli {
    /// Path to the input seed file (JSON)
    #[arg(short, long)]
    input: String,

    /// Path to the output file (JSON). Prints to stdout if omitted.
    #[arg(short, long)]
    output: Option<String>,

    /// Batch mode: treat --input as a directory of seed files
    #[arg(long, default_value_t = false)]
    batch: bool,
}

fn main() {
    let cli = Cli::parse();

    if cli.batch {
        run_batch(&cli.input, cli.output.as_deref());
    } else {
        run_single(&cli.input, cli.output.as_deref());
    }
}

fn run_single(input_path: &str, output_path: Option<&str>) {
    let content = fs::read_to_string(input_path)
        .unwrap_or_else(|e| {
            eprintln!("Error reading {}: {}", input_path, e);
            std::process::exit(1);
        });

    let seed: SeedData = serde_json::from_str(&content)
        .unwrap_or_else(|e| {
            eprintln!("Error parsing seed JSON: {}", e);
            std::process::exit(1);
        });

    if let Err(msg) = sim::validate_seed(&seed) {
        eprintln!("Invalid seed data: {}", msg);
        std::process::exit(1);
    }

    let output = sim::run_simulation(&seed);

    let json_str = format_output_truncated(&output);

    match output_path {
        Some(path) => fs::write(path, &json_str).unwrap_or_else(|e| {
            eprintln!("Error writing {}: {}", path, e);
            std::process::exit(1);
        }),
        None => print!("{}", json_str),
    }
}

fn run_batch(input_dir: &str, output_path: Option<&str>) {
    eprintln!("Batch mode not yet implemented");
    eprintln!("Input directory: {}", input_dir);
    if let Some(p) = output_path {
        eprintln!("Output path: {}", p);
    }
    std::process::exit(1);
}

/// Format simulation output as JSON.
fn format_output_truncated(output: &SimOutput) -> String {
    let mut s = String::with_capacity(4096);
    s.push_str("{\"steps\":[");
    for (i, step) in output.steps.iter().enumerate() {
        if i > 0 {
            s.push(',');
        }
        s.push_str(&format!("{{\"time\":{:.2},\"bodies\":[", step.time));
        for (j, body) in step.bodies.iter().enumerate() {
            if j > 0 {
                s.push(',');
            }
            s.push_str(&format!(
                "{{\"position\":[{:.2},{:.2},{:.2}],\"velocity\":[{:.2},{:.2},{:.2}],\"ke\":{:.2},\"pe\":{:.2}}}",
                body.position[0], body.position[1], body.position[2],
                body.velocity[0], body.velocity[1], body.velocity[2],
                body.ke, body.pe
            ));
        }
        s.push_str(&format!("],\"total_energy\":{:.2}}}", step.total_energy));
    }
    s.push_str("],\"collisions\":[");
    for (i, col) in output.collisions.iter().enumerate() {
        if i > 0 {
            s.push(',');
        }
        s.push_str(&format!(
            "{{\"step\":{},\"body_a\":{},\"body_b\":{},\"distance\":{:.2}}}",
            col.step, col.body_a, col.body_b, col.distance
        ));
    }
    s.push_str("]}");
    s
}
