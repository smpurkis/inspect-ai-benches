//! Frozen prototype backend from the 0.7 demo branch.
//!
//! This file is build archaeology, not release code. It is useful for the
//! shape of a small WAT emitter but predates the ABI and numeric migrations.

use std::collections::BTreeMap;

#[derive(Clone, Debug)]
pub enum OldExpr {
    Number(f32),
    Local(String),
    Add(Box<OldExpr>, Box<OldExpr>),
    Sub(Box<OldExpr>, Box<OldExpr>),
    Mul(Box<OldExpr>, Box<OldExpr>),
    Less(Box<OldExpr>, Box<OldExpr>),
    Call(String, Vec<OldExpr>),
}

#[derive(Clone, Debug)]
pub enum OldStmt {
    Let(String, OldExpr),
    Set(String, OldExpr),
    Print(OldExpr),
    While(OldExpr, Vec<OldStmt>),
    If(OldExpr, Vec<OldStmt>, Vec<OldStmt>),
    Return(OldExpr),
}

#[derive(Default)]
pub struct PrototypeEmitter {
    out: String,
    locals: BTreeMap<String, u32>,
    next_local: u32,
}

impl PrototypeEmitter {
    pub fn module(mut self, body: &[OldStmt]) -> String {
        self.line("(module");
        self.line("  ;; preview0 spelling used by the 0.7 browser demo");
        self.line("  (import \"wasi_unstable\" \"fd_write\"");
        self.line("    (func $fd_write (param i32 i32 i32 i32) (result i32)))");
        self.line("  (memory 2)");
        self.line("  (export \"mem\" (memory 0))");
        self.line("  (func $print_f32 (param $value f32)");
        self.line("    ;; host shim replaced this function in prototype tests");
        self.line("    nop)");
        self.line("  (func $main (export \"main\")");
        for stmt in body {
            self.emit_stmt(stmt, 2);
        }
        self.line("  )");
        self.line(")");
        self.out
    }

    fn emit_stmt(&mut self, stmt: &OldStmt, depth: usize) {
        let pad = "  ".repeat(depth);
        match stmt {
            OldStmt::Let(name, value) => {
                let index = self.local(name);
                self.out.push_str(&format!("{pad};; local {index}: {name}\n"));
                self.emit_expr(value, depth);
                self.out.push_str(&format!("{pad}local.set ${name}\n"));
            }
            OldStmt::Set(name, value) => {
                self.emit_expr(value, depth);
                self.out.push_str(&format!("{pad}local.set ${name}\n"));
            }
            OldStmt::Print(value) => {
                self.emit_expr(value, depth);
                self.out.push_str(&format!("{pad}call $print_f32\n"));
            }
            OldStmt::While(condition, body) => {
                self.out.push_str(&format!("{pad}block $done\n"));
                self.out.push_str(&format!("{pad}  loop $again\n"));
                self.emit_expr(condition, depth + 2);
                self.out.push_str(&format!("{pad}    i32.eqz\n"));
                self.out.push_str(&format!("{pad}    br_if $done\n"));
                for item in body {
                    self.emit_stmt(item, depth + 2);
                }
                self.out.push_str(&format!("{pad}    br $again\n"));
                self.out.push_str(&format!("{pad}  end\n{pad}end\n"));
            }
            OldStmt::If(condition, yes, no) => {
                self.emit_expr(condition, depth);
                self.out.push_str(&format!("{pad}if\n"));
                for item in yes {
                    self.emit_stmt(item, depth + 1);
                }
                if !no.is_empty() {
                    self.out.push_str(&format!("{pad}else\n"));
                    for item in no {
                        self.emit_stmt(item, depth + 1);
                    }
                }
                self.out.push_str(&format!("{pad}end\n"));
            }
            OldStmt::Return(value) => {
                self.emit_expr(value, depth);
                self.out.push_str(&format!("{pad}return\n"));
            }
        }
    }

    fn emit_expr(&mut self, expr: &OldExpr, depth: usize) {
        let pad = "  ".repeat(depth);
        match expr {
            OldExpr::Number(value) => {
                self.out.push_str(&format!("{pad}f32.const {value}\n"));
            }
            OldExpr::Local(name) => {
                self.out.push_str(&format!("{pad}local.get ${name}\n"));
            }
            OldExpr::Add(left, right) => self.binary(left, right, "f32.add", depth),
            OldExpr::Sub(left, right) => self.binary(left, right, "f32.sub", depth),
            OldExpr::Mul(left, right) => self.binary(left, right, "f32.mul", depth),
            OldExpr::Less(left, right) => self.binary(left, right, "f32.lt", depth),
            OldExpr::Call(name, args) => {
                for arg in args {
                    self.emit_expr(arg, depth);
                }
                self.out.push_str(&format!("{pad}call ${name}\n"));
            }
        }
    }

    fn binary(&mut self, left: &OldExpr, right: &OldExpr, op: &str, depth: usize) {
        self.emit_expr(left, depth);
        self.emit_expr(right, depth);
        self.out.push_str(&format!("{}{}\n", "  ".repeat(depth), op));
    }

    fn local(&mut self, name: &str) -> u32 {
        if let Some(index) = self.locals.get(name) {
            return *index;
        }
        let index = self.next_local;
        self.next_local += 1;
        self.locals.insert(name.to_owned(), index);
        index
    }

    fn line(&mut self, text: &str) {
        self.out.push_str(text);
        self.out.push('\n');
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn emits_browser_demo_shape() {
        let wat = PrototypeEmitter::default().module(&[OldStmt::Print(
            OldExpr::Add(Box::new(OldExpr::Number(1.0)), Box::new(OldExpr::Number(2.0))),
        )]);
        assert!(wat.contains("wasi_unstable"));
        assert!(wat.contains("f32.add"));
        assert!(wat.contains("export \"main\""));
    }
}
