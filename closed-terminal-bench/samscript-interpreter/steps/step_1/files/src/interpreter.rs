// interpreter.rs — Tree-walking interpreter for SamScript
//
// STATUS: STUBBED. You must implement a complete tree-walking interpreter.
//
// Design notes:
//   - Values are dynamically typed: use an enum (Value) with Number(f64),
//     Str(String), Bool(bool), None, List(Vec<Value>), Dict(HashMap<String, Value>).
//   - Environments are nested (scopes): use a Vec<HashMap<String, Value>> stack,
//     or a linked-list of frames.
//   - `const` variables must be tracked and rejected on reassignment.
//   - `loop` / `break` / `continue` can use Result-based control flow or a
//     special ControlFlow enum.
//   - Built-in functions (print, len, type, str, num, assert, input) are
//     pre-registered in the global scope.
//   - Entry point: find and call `main()`. If no `main` function exists,
//     emit a clear error.
//   - Errors should include line numbers and a stack trace.

use crate::ast::*;
use std::collections::HashMap;
use std::fmt;

/// Runtime values in SamScript.
#[derive(Debug, Clone)]
pub enum Value {
    Number(f64),
    Str(String),
    Bool(bool),
    None,
    List(Vec<Value>),
    Dict(Vec<(String, Value)>),
    Function {
        name: String,
        params: Vec<Param>,
        body: Vec<Stmt>,
    },
    BuiltinFn(String),
}

impl fmt::Display for Value {
