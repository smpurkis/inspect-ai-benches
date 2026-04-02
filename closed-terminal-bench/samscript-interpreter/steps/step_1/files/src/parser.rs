// parser.rs — Recursive-descent parser for SamScript
//
// STATUS: STUBBED. All function bodies contain todo!().
// You must implement a complete recursive-descent parser that converts
// a token stream into the AST defined in ast.rs.
//
// Suggested structure:
//   - parse() is the entry point: parse top-level fn declarations and imports
//   - parse_fn_decl() parses `fn name(params) { body }`
//   - parse_stmt() dispatches on the current token
//   - parse_expr() uses Pratt parsing or recursive descent for precedence
//   - parse_primary() handles literals, identifiers, parenthesized exprs, etc.
//
// Precedence (low to high):
//   or < and < == != < < > <= >= < + - .. < * / % < ** < unary(- not) < call/index

use crate::ast::*;
use crate::lexer::{SpannedToken, Token};

#[derive(Debug)]
pub struct ParseError {
    pub line: usize,
    pub message: String,
}

struct Parser {
    tokens: Vec<SpannedToken>,
    pos: usize,
}

impl Parser {
    fn new(tokens: Vec<SpannedToken>) -> Self {
        Parser { tokens, pos: 0 }
    }

    fn current(&self) -> &Token {
        self.tokens
            .get(self.pos)
            .map(|t| &t.token)
            .unwrap_or(&Token::Eof)
    }

    fn current_line(&self) -> usize {
        self.tokens
            .get(self.pos)
            .map(|t| t.line)
            .unwrap_or(0)
    }

    fn advance(&mut self) -> &Token {
        let tok = self.current().clone();
        self.pos += 1;
        self.tokens
            .get(self.pos - 1)
            .map(|t| &t.token)
            .unwrap_or(&Token::Eof)
    }

    fn skip_newlines(&mut self) {
        while self.current() == &Token::Newline {
            self.advance();
        }
    }

    fn expect(&mut self, expected: &Token) -> Result<(), ParseError> {
        if self.current() == expected {
            self.advance();
            Ok(())
        } else {
            Err(ParseError {
                line: self.current_line(),
                message: format!("expected {:?}, got {:?}", expected, self.current()),
            })
        }
    }

    // ── Top-level parsing ──────────────────────────────────────────────

    fn parse_program(&mut self) -> Result<Program, ParseError> {
        todo!("parse_program: iterate top-level items (fn decls, imports) until Eof")
    }

    fn parse_import_decl(&mut self) -> Result<ImportDecl, ParseError> {
        todo!("parse_import_decl: from <module> import <name1>, <name2>")
    }

    fn parse_fn_decl(&mut self) -> Result<FnDecl, ParseError> {
        todo!("parse_fn_decl: fn <name>(<params>) [-> <type>] {{ <body> }}")
    }

    fn parse_params(&mut self) -> Result<Vec<Param>, ParseError> {
        todo!("parse_params: name [: type] [= default], ...")
    }

    // ── Statement parsing ──────────────────────────────────────────────

    fn parse_block(&mut self) -> Result<Vec<Stmt>, ParseError> {
        todo!("parse_block: {{ stmt; stmt; ... }}")
    }

    fn parse_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_stmt: dispatch on current token (let, const, if, loop, break, continue, return, from, or expr)")
    }

    fn parse_let_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_let_stmt: let <name> = <expr>")
    }

    fn parse_const_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_const_stmt: const <name> = <expr>")
    }

    fn parse_if_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_if_stmt: if <expr> {{ ... }} [else if <expr> {{ ... }}]* [else {{ ... }}]")
    }

    fn parse_loop_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_loop_stmt: loop {{ ... }}")
    }

    fn parse_return_stmt(&mut self) -> Result<Stmt, ParseError> {
        todo!("parse_return_stmt: return [<expr>]")
    }

    // ── Expression parsing (Pratt / precedence climbing) ───────────────

    fn parse_expr(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_expr: entry point for expression parsing, delegates to parse_or")
    }

    fn parse_or(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_or: left-associative 'or'")
    }

    fn parse_and(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_and: left-associative 'and'")
    }

    fn parse_equality(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_equality: == and !=")
    }

    fn parse_comparison(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_comparison: < > <= >=")
    }

    fn parse_addition(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_addition: + - ..")
    }

    fn parse_multiplication(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_multiplication: * / %")
    }

    fn parse_power(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_power: ** (right-associative)")
    }

    fn parse_unary(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_unary: - not")
    }

    fn parse_postfix(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_postfix: function calls f(...), indexing a[i], field access a.x")
    }

    fn parse_primary(&mut self) -> Result<Expr, ParseError> {
        todo!("parse_primary: number, string, interp string, bool, none, ident, ( expr ), [ list ], {{ dict }}")
    }
}

/// Parse a token stream into a SamScript Program AST.
pub fn parse(tokens: Vec<SpannedToken>) -> Result<Program, ParseError> {
    let mut parser = Parser::new(tokens);
    parser.parse_program()
}
