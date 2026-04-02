mod ast;
mod compiler;
mod interpreter;
mod lexer;
mod parser;

use clap::{Parser, Subcommand};
use std::path::PathBuf;
use std::process;

#[derive(Parser)]
#[command(name = "samscript", version, about = "SamScript language toolchain")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Interpret a SamScript source file
    Run {
        /// Path to the .sam source file
        file: PathBuf,
    },
    /// Compile a SamScript source file to a native executable
    Compile {
        /// Path to the .sam source file
        file: PathBuf,
        /// Output path for the compiled binary
        #[arg(short, long, default_value = "a.out")]
        output: PathBuf,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Run { file } => {
            let source = match std::fs::read_to_string(&file) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("error: could not read '{}': {}", file.display(), e);
                    process::exit(1);
                }
            };

            let tokens = match lexer::tokenize(&source) {
                Ok(t) => t,
                Err(e) => {
                    eprintln!("lexer error at line {}: {}", e.line, e.message);
                    process::exit(1);
                }
            };

            let program = match parser::parse(tokens) {
                Ok(p) => p,
                Err(e) => {
                    eprintln!("parse error at line {}: {}", e.line, e.message);
                    process::exit(1);
                }
            };

            if let Err(e) = interpreter::interpret(&program) {
                eprintln!(
                    "runtime error at line {}: {}\nstack trace:\n{}",
                    e.line, e.message, e.stack_trace
                );
                process::exit(1);
            }
        }
        Commands::Compile { file, output } => {
            let source = match std::fs::read_to_string(&file) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("error: could not read '{}': {}", file.display(), e);
                    process::exit(1);
                }
            };

            let tokens = match lexer::tokenize(&source) {
                Ok(t) => t,
                Err(e) => {
                    eprintln!("lexer error at line {}: {}", e.line, e.message);
                    process::exit(1);
                }
            };

            let program = match parser::parse(tokens) {
                Ok(p) => p,
                Err(e) => {
                    eprintln!("parse error at line {}: {}", e.line, e.message);
                    process::exit(1);
                }
            };

            let output_str = output.to_str().unwrap_or("a.out");
            if let Err(e) = compiler::compile(&program, output_str) {
                eprintln!("compile error: {}", e.message);
                process::exit(1);
            }
        }
    }
}
