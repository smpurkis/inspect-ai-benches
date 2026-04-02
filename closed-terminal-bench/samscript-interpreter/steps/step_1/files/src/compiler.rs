// compiler.rs — Native code compiler for SamScript using Cranelift
//
// STATUS: STUBBED. You must implement compilation from the SamScript AST
// to native machine code using the Cranelift code generator.
//
// Design notes:
//   - Use cranelift_codegen, cranelift_frontend, cranelift_module, cranelift_object
//     to build an object file, then link it into an executable.
//   - All SamScript values are dynamically typed at runtime, so the compiled code
//     must use a tagged-union representation (e.g., a 16-byte struct: 8-byte tag +
//     8-byte payload, or a pointer to a heap-allocated Value).
//   - Strategy options:
//     (a) Compile to a bytecode + embed an interpreter in the binary
//     (b) Full native compilation with Cranelift IR for each function
//     (c) Hybrid: compile hot paths, interpret cold paths
//   - The compiled binary MUST produce identical output to the interpreter for
//     all valid programs. This parity is tested.
//   - Built-in functions (print, len, type, etc.) must be linked into the
//     compiled binary — either as Rust helper functions compiled into the
//     object file, or as a small runtime library.
//   - For string interpolation, the compiled code must evaluate sub-expressions
//     and concatenate the results, matching interpreter behavior exactly.
//
// Suggested approach:
//   1. Define a runtime library (functions like rt_print, rt_add, rt_concat, etc.)
//   2. Compile each SamScript function to Cranelift IR that calls runtime functions
//   3. Emit the object file using cranelift_object
//   4. Link with the system linker (cc) to produce the final executable

use crate::ast::*;

#[derive(Debug)]
pub struct CompileError {
    pub message: String,
}

/// Compile a SamScript program to a native executable at the given output path.
///
/// The compiled binary must produce identical output to the interpreter.
pub fn compile(program: &Program, output_path: &str) -> Result<(), CompileError> {
