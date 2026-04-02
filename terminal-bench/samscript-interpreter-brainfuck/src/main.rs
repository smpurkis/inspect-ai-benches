use std::collections::HashMap;
use std::fs;
use std::process;
use clap::{Parser as ClapParser, Subcommand};

// ===== Error =====

#[derive(Debug, Clone)]
struct SamError {
    msg: String,
    line: usize,
}

impl std::fmt::Display for SamError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        if self.line > 0 {
            write!(f, "error at line {}: {}", self.line, self.msg)
        } else {
            write!(f, "error: {}", self.msg)
        }
    }
}

// ===== Tokens =====

#[derive(Debug, Clone, PartialEq)]
enum Tok {
    Num(f64),
    Str(String),
    InterpStr(Vec<StringPart>),
    True, False, NoneLit,
    Ident(String),
    Fn, Let, Const, If, Else, Loop, Break, Continue, Return,
    From, Import, And, Or, Not,
    Plus, Minus, Star, Slash, Percent, StarStar, DotDot,
    EqEq, BangEq, Lt, Gt, LtEq, GtEq,
    Eq, PlusEq, MinusEq, StarEq, SlashEq, PercentEq,
    LParen, RParen, LBrace, RBrace, LBracket, RBracket,
    Comma, Colon, Arrow,
    Newline, Eof,
}

#[derive(Debug, Clone, PartialEq)]
enum StringPart {
    Lit(String),
    Expr(String), // raw expression source inside ${}
}

#[derive(Debug, Clone)]
struct Token {
    kind: Tok,
    line: usize,
}

// ===== AST =====

#[derive(Debug, Clone)]
enum Expr {
    Num(f64),
    Str(String),
    Interp(Vec<InterpPart>),
    Bool(bool),
    NoneLit,
    Var(String),
    BinOp { left: Box<Expr>, op: BinOp, right: Box<Expr> },
    UnaryOp { op: UnaryOp, operand: Box<Expr> },
    Call { name: String, args: Vec<Expr> },
    Index { object: Box<Expr>, index: Box<Expr> },
    List(Vec<Expr>),
    Dict(Vec<(Expr, Expr)>),
}

#[derive(Debug, Clone)]
enum InterpPart {
    Lit(String),
    Expr(Box<Expr>),
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum BinOp {
    Add, Sub, Mul, Div, Mod, Pow,
    Concat,
    Eq, Ne, Lt, Gt, Le, Ge,
    And, Or,
}

#[derive(Debug, Clone, Copy, PartialEq)]
enum UnaryOp { Neg, Not }

#[derive(Debug, Clone)]
enum Stmt {
    Expr(Expr),
    Let { name: String, value: Expr },
    Const { name: String, value: Expr },
    Assign { name: String, value: Expr },
    IndexAssign { object: Expr, index: Expr, value: Expr },
    CompoundAssign { name: String, op: BinOp, value: Expr },
    If {
        cond: Expr,
        body: Vec<Stmt>,
        else_ifs: Vec<(Expr, Vec<Stmt>)>,
        else_body: Option<Vec<Stmt>>,
    },
    Loop(Vec<Stmt>),
    Break,
    Continue,
    Return(Option<Expr>),
}

#[derive(Debug, Clone)]
struct Param {
    name: String,
    default: Option<Expr>,
}

#[derive(Debug, Clone)]
struct FnDecl {
    name: String,
    params: Vec<Param>,
    body: Vec<Stmt>,
}

#[derive(Debug, Clone)]
struct Program {
    functions: Vec<FnDecl>,
}

// ===== Lexer =====

fn tokenize(source: &str) -> Result<Vec<Token>, SamError> {
    let chars: Vec<char> = source.chars().collect();
    let len = chars.len();
    let mut tokens: Vec<Token> = Vec::new();
    let mut i = 0;
    let mut line: usize = 1;

    while i < len {
        let c = chars[i];

        // Skip spaces and tabs
        if c == ' ' || c == '\t' || c == '\r' {
            i += 1;
            continue;
        }

        // Newlines
        if c == '\n' {
            // Collapse consecutive newlines into one token
            if tokens.is_empty() || tokens.last().map_or(true, |t| t.kind == Tok::Newline) {
                // skip — don't emit duplicate newlines, and don't emit leading newlines
                line += 1;
                i += 1;
                continue;
            }
            tokens.push(Token { kind: Tok::Newline, line });
            line += 1;
            i += 1;
            // Consume any following blank lines
            while i < len {
                if chars[i] == '\n' {
                    line += 1;
                    i += 1;
                } else if chars[i] == ' ' || chars[i] == '\t' || chars[i] == '\r' {
                    i += 1;
                } else {
                    break;
                }
            }
            continue;
        }

        // Comments
        if c == '/' && i + 1 < len && chars[i + 1] == '/' {
            i += 2;
            while i < len && chars[i] != '\n' {
                i += 1;
            }
            continue;
        }

        // Numbers
        if c.is_ascii_digit() {
            let start = i;
            while i < len && chars[i].is_ascii_digit() {
                i += 1;
            }
            if i < len && chars[i] == '.' && i + 1 < len && chars[i + 1].is_ascii_digit() {
                i += 1; // skip dot
                while i < len && chars[i].is_ascii_digit() {
                    i += 1;
                }
            }
            let num_str: String = chars[start..i].iter().collect();
            let val: f64 = num_str.parse().map_err(|_| SamError {
                msg: format!("invalid number: {}", num_str),
                line,
            })?;
            tokens.push(Token { kind: Tok::Num(val), line });
            continue;
        }

        // Strings
        if c == '"' {
            let string_start_line = line;
            i += 1; // skip opening quote
            let mut parts: Vec<StringPart> = Vec::new();
            let mut current_lit = String::new();
            let mut has_interp = false;

            while i < len && chars[i] != '"' {
                if chars[i] == '\n' {
                    line += 1;
                    current_lit.push('\n');
                    i += 1;
                } else if chars[i] == '\\' {
                    i += 1;
                    if i >= len {
                        return Err(SamError {
                            msg: "unterminated string escape".to_string(),
                            line: string_start_line,
                        });
                    }
                    match chars[i] {
                        'n' => current_lit.push('\n'),
                        't' => current_lit.push('\t'),
                        '\\' => current_lit.push('\\'),
                        '"' => current_lit.push('"'),
                        '$' => current_lit.push('$'),
                        other => {
                            current_lit.push('\\');
                            current_lit.push(other);
                        }
                    }
                    i += 1;
                } else if chars[i] == '$' && i + 1 < len && chars[i + 1] == '{' {
                    // String interpolation
                    has_interp = true;
                    if !current_lit.is_empty() {
                        parts.push(StringPart::Lit(current_lit.clone()));
                        current_lit.clear();
                    }
                    i += 2; // skip ${
                    let mut depth = 1;
                    let mut expr_src = String::new();
                    while i < len && depth > 0 {
                        if chars[i] == '{' {
                            depth += 1;
                            expr_src.push('{');
                        } else if chars[i] == '}' {
                            depth -= 1;
                            if depth > 0 {
                                expr_src.push('}');
                            }
                        } else {
                            if chars[i] == '\n' {
                                line += 1;
                            }
                            expr_src.push(chars[i]);
                        }
                        i += 1;
                    }
                    if depth != 0 {
                        return Err(SamError {
                            msg: "unterminated string interpolation".to_string(),
                            line: string_start_line,
                        });
                    }
                    parts.push(StringPart::Expr(expr_src));
                } else {
                    current_lit.push(chars[i]);
                    i += 1;
                }
            }

            if i >= len {
                return Err(SamError {
                    msg: "unterminated string".to_string(),
                    line: string_start_line,
                });
            }
            i += 1; // skip closing quote

            if has_interp {
                if !current_lit.is_empty() {
                    parts.push(StringPart::Lit(current_lit));
                }
                tokens.push(Token { kind: Tok::InterpStr(parts), line: string_start_line });
            } else {
                tokens.push(Token { kind: Tok::Str(current_lit), line: string_start_line });
            }
            continue;
        }

        // Identifiers and keywords
        if c.is_ascii_alphabetic() || c == '_' {
            let start = i;
            while i < len && (chars[i].is_ascii_alphanumeric() || chars[i] == '_') {
                i += 1;
            }
            let word: String = chars[start..i].iter().collect();
            let kind = match word.as_str() {
                "fn" => Tok::Fn,
                "let" => Tok::Let,
                "const" => Tok::Const,
                "if" => Tok::If,
                "else" => Tok::Else,
                "loop" => Tok::Loop,
                "break" => Tok::Break,
                "continue" => Tok::Continue,
                "return" => Tok::Return,
                "from" => Tok::From,
                "import" => Tok::Import,
                "and" => Tok::And,
                "or" => Tok::Or,
                "not" => Tok::Not,
                "true" => Tok::True,
                "false" => Tok::False,
                "none" => Tok::NoneLit,
                _ => Tok::Ident(word),
            };
            tokens.push(Token { kind, line });
            continue;
        }

        // Two-char operators (check before single-char)
        if i + 1 < len {
            let c2 = chars[i + 1];
            let two: Option<Tok> = match (c, c2) {
                ('=', '=') => Some(Tok::EqEq),
                ('!', '=') => Some(Tok::BangEq),
                ('<', '=') => Some(Tok::LtEq),
                ('>', '=') => Some(Tok::GtEq),
                ('*', '*') => Some(Tok::StarStar),
                ('.', '.') => Some(Tok::DotDot),
                ('+', '=') => Some(Tok::PlusEq),
                ('-', '=') => Some(Tok::MinusEq),
                ('*', '=') => Some(Tok::StarEq),
                ('/', '=') => Some(Tok::SlashEq),
                ('%', '=') => Some(Tok::PercentEq),
                ('-', '>') => Some(Tok::Arrow),
                _ => None,
            };
            if let Some(kind) = two {
                tokens.push(Token { kind, line });
                i += 2;
                continue;
            }
        }

        // Single-char operators and delimiters
        let single: Option<Tok> = match c {
            '+' => Some(Tok::Plus),
            '-' => Some(Tok::Minus),
            '*' => Some(Tok::Star),
            '/' => Some(Tok::Slash),
            '%' => Some(Tok::Percent),
            '<' => Some(Tok::Lt),
            '>' => Some(Tok::Gt),
            '=' => Some(Tok::Eq),
            '(' => Some(Tok::LParen),
            ')' => Some(Tok::RParen),
            '{' => Some(Tok::LBrace),
            '}' => Some(Tok::RBrace),
            '[' => Some(Tok::LBracket),
            ']' => Some(Tok::RBracket),
            ',' => Some(Tok::Comma),
            ':' => Some(Tok::Colon),
            _ => None,
        };

        if let Some(kind) = single {
            tokens.push(Token { kind, line });
            i += 1;
            continue;
        }

        return Err(SamError {
            msg: format!("unexpected character: {:?}", c),
            line,
        });
    }

    // Remove trailing newline if present
    if let Some(last) = tokens.last() {
        if last.kind == Tok::Newline {
            tokens.pop();
        }
    }

    tokens.push(Token { kind: Tok::Eof, line });
    Ok(tokens)
}

// ===== Parser =====

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
}

impl Parser {
    fn new(tokens: Vec<Token>) -> Self {
        Parser { tokens, pos: 0 }
    }

    fn peek(&self) -> &Tok {
        if self.pos < self.tokens.len() {
            &self.tokens[self.pos].kind
        } else {
            &Tok::Eof
        }
    }

    fn current_line(&self) -> usize {
        if self.pos < self.tokens.len() {
            self.tokens[self.pos].line
        } else if !self.tokens.is_empty() {
            self.tokens[self.tokens.len() - 1].line
        } else {
            0
        }
    }

    fn advance(&mut self) -> Token {
        let tok = if self.pos < self.tokens.len() {
            self.tokens[self.pos].clone()
        } else {
            Token { kind: Tok::Eof, line: self.current_line() }
        };
        self.pos += 1;
        tok
    }

    fn expect(&mut self, expected: &Tok) -> Result<Token, SamError> {
        let tok = self.advance();
        if std::mem::discriminant(&tok.kind) == std::mem::discriminant(expected) {
            Ok(tok)
        } else {
            Err(SamError {
                msg: format!("expected {:?}, found {:?}", expected, tok.kind),
                line: tok.line,
            })
        }
    }

    fn expect_ident(&mut self) -> Result<(String, usize), SamError> {
        let tok = self.advance();
        if let Tok::Ident(name) = tok.kind {
            Ok((name, tok.line))
        } else {
            Err(SamError {
                msg: format!("expected identifier, found {:?}", tok.kind),
                line: tok.line,
            })
        }
    }

    fn skip_newlines(&mut self) {
        while self.pos < self.tokens.len() && self.tokens[self.pos].kind == Tok::Newline {
            self.pos += 1;
        }
    }

    fn at(&self, expected: &Tok) -> bool {
        std::mem::discriminant(self.peek()) == std::mem::discriminant(expected)
    }

    fn at_end(&self) -> bool {
        matches!(self.peek(), Tok::Eof)
    }

    // ---- Program parsing ----

    fn parse_program(&mut self) -> Result<Program, SamError> {
        let mut functions = Vec::new();
        self.skip_newlines();
        while !self.at_end() {
            if *self.peek() == Tok::From {
                // from X import Y, Z — skip these for now (parser ignores imports)
                self.parse_import()?;
            } else {
                functions.push(self.parse_fn_decl()?);
            }
            self.skip_newlines();
        }
        Ok(Program { functions })
    }

    fn parse_import(&mut self) -> Result<(), SamError> {
        self.expect(&Tok::From)?;
        self.expect_ident()?; // module name
        self.expect(&Tok::Import)?;
        self.expect_ident()?; // first name
        while *self.peek() == Tok::Comma {
            self.advance();
            self.expect_ident()?;
        }
        self.skip_newlines();
        Ok(())
    }

    fn parse_fn_decl(&mut self) -> Result<FnDecl, SamError> {
        self.expect(&Tok::Fn)?;
        let (name, _) = self.expect_ident()?;
        self.expect(&Tok::LParen)?;
        let params = self.parse_params()?;
        self.expect(&Tok::RParen)?;

        // Optional return type annotation: -> type
        if *self.peek() == Tok::Arrow {
            self.advance(); // skip ->
            self.expect_ident()?; // skip type name
        }

        self.skip_newlines();
        let body = self.parse_block()?;
        self.skip_newlines();
        Ok(FnDecl { name, params, body })
    }

    fn parse_params(&mut self) -> Result<Vec<Param>, SamError> {
        let mut params = Vec::new();
        if *self.peek() == Tok::RParen {
            return Ok(params);
        }
        loop {
            self.skip_newlines();
            let (name, _) = self.expect_ident()?;

            // Optional type annotation: name: type
            if *self.peek() == Tok::Colon {
                self.advance(); // skip :
                self.expect_ident()?; // skip type name
            }

            let default = if *self.peek() == Tok::Eq {
                self.advance();
                Some(self.parse_expr()?)
            } else {
                None
            };
            params.push(Param { name, default });
            self.skip_newlines();
            if *self.peek() == Tok::Comma {
                self.advance();
            } else {
                break;
            }
        }
        Ok(params)
    }

    fn parse_block(&mut self) -> Result<Vec<Stmt>, SamError> {
        self.skip_newlines();
        self.expect(&Tok::LBrace)?;
        self.skip_newlines();
        let mut stmts = Vec::new();
        while *self.peek() != Tok::RBrace && !self.at_end() {
            stmts.push(self.parse_stmt()?);
            self.skip_newlines();
        }
        self.expect(&Tok::RBrace)?;
        Ok(stmts)
    }

    // ---- Statement parsing ----

    fn parse_stmt(&mut self) -> Result<Stmt, SamError> {
        self.skip_newlines();
        match self.peek().clone() {
            Tok::Let => self.parse_let(),
            Tok::Const => self.parse_const(),
            Tok::If => self.parse_if(),
            Tok::Loop => self.parse_loop(),
            Tok::Break => { self.advance(); self.eat_newline(); Ok(Stmt::Break) }
            Tok::Continue => { self.advance(); self.eat_newline(); Ok(Stmt::Continue) }
            Tok::Return => self.parse_return(),
            _ => self.parse_expr_or_assign_stmt(),
        }
    }

    fn eat_newline(&mut self) {
        if *self.peek() == Tok::Newline {
            self.advance();
        }
    }

    fn parse_let(&mut self) -> Result<Stmt, SamError> {
        self.advance(); // consume 'let'
        let (name, _) = self.expect_ident()?;
        self.expect(&Tok::Eq)?;
        let value = self.parse_expr()?;
        self.eat_newline();
        Ok(Stmt::Let { name, value })
    }

    fn parse_const(&mut self) -> Result<Stmt, SamError> {
        self.advance(); // consume 'const'
        let (name, _) = self.expect_ident()?;
        self.expect(&Tok::Eq)?;
        let value = self.parse_expr()?;
        self.eat_newline();
        Ok(Stmt::Const { name, value })
    }

    fn parse_if(&mut self) -> Result<Stmt, SamError> {
        self.advance(); // consume 'if'
        let cond = self.parse_expr()?;
        let body = self.parse_block()?;

        let mut else_ifs = Vec::new();
        let mut else_body = None;

        self.skip_newlines();
        while *self.peek() == Tok::Else {
            self.advance(); // consume 'else'
            if *self.peek() == Tok::If {
                self.advance(); // consume 'if'
                let eicond = self.parse_expr()?;
                let eibody = self.parse_block()?;
                else_ifs.push((eicond, eibody));
                self.skip_newlines();
            } else {
                else_body = Some(self.parse_block()?);
                break;
            }
        }

        Ok(Stmt::If { cond, body, else_ifs, else_body })
    }

    fn parse_loop(&mut self) -> Result<Stmt, SamError> {
        self.advance(); // consume 'loop'
        let body = self.parse_block()?;
        Ok(Stmt::Loop(body))
    }

    fn parse_return(&mut self) -> Result<Stmt, SamError> {
        self.advance(); // consume 'return'
        // return without value: followed by newline, }, or EOF
        match self.peek() {
            Tok::Newline | Tok::RBrace | Tok::Eof => {
                self.eat_newline();
                Ok(Stmt::Return(None))
            }
            _ => {
                let val = self.parse_expr()?;
                self.eat_newline();
                Ok(Stmt::Return(Some(val)))
            }
        }
    }

    fn parse_expr_or_assign_stmt(&mut self) -> Result<Stmt, SamError> {
        // Check for: IDENT = EXPR, IDENT op= EXPR, or expr[idx] = EXPR
        // We need to handle assignment targets

        // First, check for simple name-based assignments: IDENT = ... or IDENT op= ...
        if let Tok::Ident(_) = self.peek() {
            if self.pos + 1 < self.tokens.len() {
                let next = &self.tokens[self.pos + 1].kind;
                match next {
                    Tok::Eq => {
                        let (name, _) = self.expect_ident()?;
                        self.advance(); // consume =
                        let value = self.parse_expr()?;
                        self.eat_newline();
                        return Ok(Stmt::Assign { name, value });
                    }
                    Tok::PlusEq | Tok::MinusEq | Tok::StarEq | Tok::SlashEq | Tok::PercentEq => {
                        let (name, _) = self.expect_ident()?;
                        let op_tok = self.advance();
                        let op = match op_tok.kind {
                            Tok::PlusEq => BinOp::Add,
                            Tok::MinusEq => BinOp::Sub,
                            Tok::StarEq => BinOp::Mul,
                            Tok::SlashEq => BinOp::Div,
                            Tok::PercentEq => BinOp::Mod,
                            _ => unreachable!(),
                        };
                        let value = self.parse_expr()?;
                        self.eat_newline();
                        return Ok(Stmt::CompoundAssign { name, op, value });
                    }
                    _ => {}
                }
            }
        }

        // Otherwise, parse as expression; it may be an index-assign
        let expr = self.parse_expr()?;

        // Check for index assignment: expr[idx] = value
        if *self.peek() == Tok::Eq {
            // The expr must be an Index node
            if let Expr::Index { object, index } = expr {
                self.advance(); // consume =
                let value = self.parse_expr()?;
                self.eat_newline();
                return Ok(Stmt::IndexAssign { object: *object, index: *index, value });
            }
            return Err(SamError {
                msg: "invalid assignment target".to_string(),
                line: self.current_line(),
            });
        }

        self.eat_newline();
        Ok(Stmt::Expr(expr))
    }

    // ---- Expression parsing ----

    fn parse_expr(&mut self) -> Result<Expr, SamError> {
        self.parse_or()
    }

    // Precedence 1: or
    fn parse_or(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_and()?;
        while *self.peek() == Tok::Or {
            self.advance();
            let right = self.parse_and()?;
            left = Expr::BinOp { left: Box::new(left), op: BinOp::Or, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 2: and
    fn parse_and(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_equality()?;
        while *self.peek() == Tok::And {
            self.advance();
            let right = self.parse_equality()?;
            left = Expr::BinOp { left: Box::new(left), op: BinOp::And, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 3: == !=
    fn parse_equality(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_comparison()?;
        loop {
            let op = match self.peek() {
                Tok::EqEq => BinOp::Eq,
                Tok::BangEq => BinOp::Ne,
                _ => break,
            };
            self.advance();
            let right = self.parse_comparison()?;
            left = Expr::BinOp { left: Box::new(left), op, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 4: < > <= >=
    fn parse_comparison(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_add()?;
        loop {
            let op = match self.peek() {
                Tok::Lt => BinOp::Lt,
                Tok::Gt => BinOp::Gt,
                Tok::LtEq => BinOp::Le,
                Tok::GtEq => BinOp::Ge,
                _ => break,
            };
            self.advance();
            let right = self.parse_add()?;
            left = Expr::BinOp { left: Box::new(left), op, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 5: + - ..  (left-assoc)
    fn parse_add(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_mul()?;
        loop {
            let op = match self.peek() {
                Tok::Plus => BinOp::Add,
                Tok::Minus => BinOp::Sub,
                Tok::DotDot => BinOp::Concat,
                _ => break,
            };
            self.advance();
            let right = self.parse_mul()?;
            left = Expr::BinOp { left: Box::new(left), op, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 6: * / % (left-assoc)
    fn parse_mul(&mut self) -> Result<Expr, SamError> {
        let mut left = self.parse_power()?;
        loop {
            let op = match self.peek() {
                Tok::Star => BinOp::Mul,
                Tok::Slash => BinOp::Div,
                Tok::Percent => BinOp::Mod,
                _ => break,
            };
            self.advance();
            let right = self.parse_power()?;
            left = Expr::BinOp { left: Box::new(left), op, right: Box::new(right) };
        }
        Ok(left)
    }

    // Precedence 7: ** (right-assoc)
    fn parse_power(&mut self) -> Result<Expr, SamError> {
        let base = self.parse_unary()?;
        if *self.peek() == Tok::StarStar {
            self.advance();
            let exp = self.parse_power()?; // right-recursive for right-assoc
            Ok(Expr::BinOp { left: Box::new(base), op: BinOp::Pow, right: Box::new(exp) })
        } else {
            Ok(base)
        }
    }

    // Precedence 8: unary - not
    fn parse_unary(&mut self) -> Result<Expr, SamError> {
        match self.peek().clone() {
            Tok::Minus => {
                self.advance();
                let operand = self.parse_unary()?;
                Ok(Expr::UnaryOp { op: UnaryOp::Neg, operand: Box::new(operand) })
            }
            Tok::Not => {
                self.advance();
                let operand = self.parse_unary()?;
                Ok(Expr::UnaryOp { op: UnaryOp::Not, operand: Box::new(operand) })
            }
            _ => self.parse_postfix(),
        }
    }

    // Precedence 9: postfix call (args) and index [expr]
    fn parse_postfix(&mut self) -> Result<Expr, SamError> {
        let mut expr = self.parse_primary()?;
        loop {
            match self.peek() {
                Tok::LParen => {
                    // This is only valid as a call if expr is a Var
                    if let Expr::Var(name) = expr {
                        self.advance(); // consume (
                        let args = self.parse_args()?;
                        self.expect(&Tok::RParen)?;
                        expr = Expr::Call { name, args };
                    } else {
                        break;
                    }
                }
                Tok::LBracket => {
                    self.advance(); // consume [
                    self.skip_newlines();
                    let index = self.parse_expr()?;
                    self.skip_newlines();
                    self.expect(&Tok::RBracket)?;
                    expr = Expr::Index { object: Box::new(expr), index: Box::new(index) };
                }
                _ => break,
            }
        }
        Ok(expr)
    }

    fn parse_args(&mut self) -> Result<Vec<Expr>, SamError> {
        let mut args = Vec::new();
        self.skip_newlines();
        if *self.peek() == Tok::RParen {
            return Ok(args);
        }
        loop {
            self.skip_newlines();
            args.push(self.parse_expr()?);
            self.skip_newlines();
            if *self.peek() == Tok::Comma {
                self.advance();
            } else {
                break;
            }
        }
        Ok(args)
    }

    // Precedence 10: primary
    fn parse_primary(&mut self) -> Result<Expr, SamError> {
        let tok = self.peek().clone();
        match tok {
            Tok::Num(n) => {
                self.advance();
                Ok(Expr::Num(n))
            }
            Tok::Str(s) => {
                self.advance();
                Ok(Expr::Str(s))
            }
            Tok::InterpStr(parts) => {
                self.advance();
                self.parse_interp_parts(parts)
            }
            Tok::True => {
                self.advance();
                Ok(Expr::Bool(true))
            }
            Tok::False => {
                self.advance();
                Ok(Expr::Bool(false))
            }
            Tok::NoneLit => {
                self.advance();
                Ok(Expr::NoneLit)
            }
            Tok::Ident(name) => {
                self.advance();
                Ok(Expr::Var(name))
            }
            Tok::LParen => {
                self.advance();
                self.skip_newlines();
                let expr = self.parse_expr()?;
                self.skip_newlines();
                self.expect(&Tok::RParen)?;
                Ok(expr)
            }
            Tok::LBracket => {
                self.advance();
                self.parse_list()
            }
            Tok::LBrace => {
                self.advance();
                self.parse_dict()
            }
            _ => {
                Err(SamError {
                    msg: format!("unexpected token: {:?}", tok),
                    line: self.current_line(),
                })
            }
        }
    }

    fn parse_list(&mut self) -> Result<Expr, SamError> {
        let mut items = Vec::new();
        self.skip_newlines();
        if *self.peek() == Tok::RBracket {
            self.advance();
            return Ok(Expr::List(items));
        }
        loop {
            self.skip_newlines();
            items.push(self.parse_expr()?);
            self.skip_newlines();
            if *self.peek() == Tok::Comma {
                self.advance();
            } else {
                break;
            }
        }
        self.skip_newlines();
        self.expect(&Tok::RBracket)?;
        Ok(Expr::List(items))
    }

    fn parse_dict(&mut self) -> Result<Expr, SamError> {
        let mut pairs = Vec::new();
        self.skip_newlines();
        if *self.peek() == Tok::RBrace {
            self.advance();
            return Ok(Expr::Dict(pairs));
        }
        loop {
            self.skip_newlines();
            let key = self.parse_expr()?;
            self.expect(&Tok::Colon)?;
            self.skip_newlines();
            let value = self.parse_expr()?;
            pairs.push((key, value));
            self.skip_newlines();
            if *self.peek() == Tok::Comma {
                self.advance();
            } else {
                break;
            }
        }
        self.skip_newlines();
        self.expect(&Tok::RBrace)?;
        Ok(Expr::Dict(pairs))
    }

    fn parse_interp_parts(&mut self, parts: Vec<StringPart>) -> Result<Expr, SamError> {
        let mut result = Vec::new();
        for part in parts {
            match part {
                StringPart::Lit(s) => {
                    result.push(InterpPart::Lit(s));
                }
                StringPart::Expr(src) => {
                    let tokens = tokenize(&src)?;
                    let mut sub_parser = Parser::new(tokens);
                    let expr = sub_parser.parse_expr()?;
                    result.push(InterpPart::Expr(Box::new(expr)));
                }
            }
        }
        Ok(Expr::Interp(result))
    }
}

fn parse(tokens: Vec<Token>) -> Result<Program, SamError> {
    let mut parser = Parser::new(tokens);
    parser.parse_program()
}

// ---------------------------------------------------------------------------
// Value type
// ---------------------------------------------------------------------------

fn format_number(n: f64) -> String {
    if n.is_finite() && n.fract() == 0.0 {
        format!("{}", n as i64)
    } else {
        format!("{}", n)
    }
}

#[derive(Debug, Clone)]
enum Value {
    Num(f64),
    Str(String),
    Bool(bool),
    None,
    List(Vec<Value>),
    Dict(Vec<(String, Value)>),
}

impl Value {
    fn to_sam_string(&self) -> String {
        match self {
            Value::Num(n) => format_number(*n),
            Value::Str(s) => s.clone(),
            Value::Bool(b) => if *b { "true".to_string() } else { "false".to_string() },
            Value::None => "none".to_string(),
            Value::List(elems) => {
                let parts: Vec<String> = elems.iter().map(|v| v.display()).collect();
                format!("[{}]", parts.join(", "))
            }
            Value::Dict(entries) => {
                let parts: Vec<String> = entries
                    .iter()
                    .map(|(k, v)| format!("\"{}\": {}", k, v.display()))
                    .collect();
                format!("{{{}}}", parts.join(", "))
            }
        }
    }

    fn display(&self) -> String {
        match self {
            Value::Str(s) => format!("\"{}\"", s),
            other => other.to_sam_string(),
        }
    }

    fn is_truthy(&self) -> bool {
        match self {
            Value::Bool(b) => *b,
            Value::None => false,
            Value::Num(n) => *n != 0.0,
            Value::Str(s) => !s.is_empty(),
            Value::List(l) => !l.is_empty(),
            Value::Dict(d) => !d.is_empty(),
        }
    }
}

// ---------------------------------------------------------------------------
// Control-flow signal
// ---------------------------------------------------------------------------

enum Signal {
    Break,
    Continue,
    Return(Value),
    Error(SamError),
}

impl From<SamError> for Signal {
    fn from(e: SamError) -> Self {
        Signal::Error(e)
    }
}

fn err(msg: impl Into<String>, line: usize) -> Signal {
    Signal::Error(SamError {
        msg: msg.into(),
        line,
    })
}

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

struct Env {
    scopes: Vec<HashMap<String, (Value, bool)>>, // (value, is_const)
    functions: HashMap<String, FnDecl>,
    call_stack: Vec<String>,
}

impl Env {
    fn new() -> Self {
        Env {
            scopes: vec![HashMap::new()],
            functions: HashMap::new(),
            call_stack: Vec::new(),
        }
    }

    fn push_scope(&mut self) {
        self.scopes.push(HashMap::new());
    }

    fn pop_scope(&mut self) {
        self.scopes.pop();
    }

    fn declare(&mut self, name: &str, value: Value, is_const: bool) {
        if let Some(scope) = self.scopes.last_mut() {
            scope.insert(name.to_string(), (value, is_const));
        }
    }

    fn get(&self, name: &str) -> Option<Value> {
        for scope in self.scopes.iter().rev() {
            if let Some((val, _)) = scope.get(name) {
                return Some(val.clone());
            }
        }
        None
    }

    fn set(&mut self, name: &str, value: Value) -> Result<(), String> {
        for scope in self.scopes.iter_mut().rev() {
            if let Some((val, is_const)) = scope.get_mut(name) {
                if *is_const {
                    return Err(format!("cannot assign to constant '{}'", name));
                }
                *val = value;
                return Ok(());
            }
        }
        Err(format!("undefined variable '{}'", name))
    }

    fn register_functions(&mut self, program: &Program) {
        for func in &program.functions {
            self.functions.insert(func.name.clone(), func.clone());
        }
    }

    fn stack_trace(&self) -> String {
        self.call_stack
            .iter()
            .rev()
            .map(|name| format!("  at {}", name))
            .collect::<Vec<_>>()
            .join("\n")
    }
}

// ---------------------------------------------------------------------------
// Interpreter
// ---------------------------------------------------------------------------

fn eval_expr(expr: &Expr, env: &mut Env) -> Result<Value, Signal> {
    match expr {
        Expr::Num(n) => Ok(Value::Num(*n)),
        Expr::Str(s) => Ok(Value::Str(s.clone())),
        Expr::Bool(b) => Ok(Value::Bool(*b)),
        Expr::NoneLit => Ok(Value::None),

        Expr::Var(name) => {
            env.get(name).ok_or_else(|| err(format!("undefined variable '{}'", name), 0))
        }

        Expr::Interp(parts) => {
            let mut result = String::new();
            for part in parts {
                match part {
                    InterpPart::Lit(s) => result.push_str(s),
                    InterpPart::Expr(e) => {
                        let val = eval_expr(e, env)?;
                        result.push_str(&val.to_sam_string());
                    }
                }
            }
            Ok(Value::Str(result))
        }

        Expr::BinOp { left, op, right } => {
            // Short-circuit for And/Or
            match op {
                BinOp::And => {
                    let lv = eval_expr(left, env)?;
                    if !lv.is_truthy() {
                        return Ok(Value::Bool(false));
                    }
                    let rv = eval_expr(right, env)?;
                    return Ok(Value::Bool(rv.is_truthy()));
                }
                BinOp::Or => {
                    let lv = eval_expr(left, env)?;
                    if lv.is_truthy() {
                        return Ok(Value::Bool(true));
                    }
                    let rv = eval_expr(right, env)?;
                    return Ok(Value::Bool(rv.is_truthy()));
                }
                _ => {}
            }

            let lv = eval_expr(left, env)?;
            let rv = eval_expr(right, env)?;

            match op {
                BinOp::Add => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Num(a + b)),
                    (Value::Str(a), Value::Str(b)) => Ok(Value::Str(format!("{}{}", a, b))),
                    _ => Err(err(format!("cannot add {:?} and {:?}", type_name(&lv), type_name(&rv)), 0)),
                },
                BinOp::Sub => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Num(a - b)),
                    _ => Err(err("subtraction requires numbers", 0)),
                },
                BinOp::Mul => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Num(a * b)),
                    _ => Err(err("multiplication requires numbers", 0)),
                },
                BinOp::Div => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => {
                        if *b == 0.0 {
                            Err(err("division by zero", 0))
                        } else {
                            Ok(Value::Num(a / b))
                        }
                    }
                    _ => Err(err("division requires numbers", 0)),
                },
                BinOp::Mod => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => {
                        if *b == 0.0 {
                            Err(err("modulo by zero", 0))
                        } else {
                            Ok(Value::Num(a % b))
                        }
                    }
                    _ => Err(err("modulo requires numbers", 0)),
                },
                BinOp::Pow => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Num(a.powf(*b))),
                    _ => Err(err("exponentiation requires numbers", 0)),
                },
                BinOp::Concat => {
                    let ls = lv.to_sam_string();
                    let rs = rv.to_sam_string();
                    Ok(Value::Str(format!("{}{}", ls, rs)))
                }
                BinOp::Eq => Ok(Value::Bool(values_equal(&lv, &rv))),
                BinOp::Ne => Ok(Value::Bool(!values_equal(&lv, &rv))),
                BinOp::Lt => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Bool(a < b)),
                    (Value::Str(a), Value::Str(b)) => Ok(Value::Bool(a < b)),
                    _ => Err(err("comparison requires matching types", 0)),
                },
                BinOp::Gt => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Bool(a > b)),
                    (Value::Str(a), Value::Str(b)) => Ok(Value::Bool(a > b)),
                    _ => Err(err("comparison requires matching types", 0)),
                },
                BinOp::Le => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Bool(a <= b)),
                    (Value::Str(a), Value::Str(b)) => Ok(Value::Bool(a <= b)),
                    _ => Err(err("comparison requires matching types", 0)),
                },
                BinOp::Ge => match (&lv, &rv) {
                    (Value::Num(a), Value::Num(b)) => Ok(Value::Bool(a >= b)),
                    (Value::Str(a), Value::Str(b)) => Ok(Value::Bool(a >= b)),
                    _ => Err(err("comparison requires matching types", 0)),
                },
                BinOp::And | BinOp::Or => unreachable!(), // handled above
            }
        }

        Expr::UnaryOp { op, operand } => {
            let val = eval_expr(operand, env)?;
            match op {
                UnaryOp::Neg => match val {
                    Value::Num(n) => Ok(Value::Num(-n)),
                    _ => Err(err("negation requires a number", 0)),
                },
                UnaryOp::Not => Ok(Value::Bool(!val.is_truthy())),
            }
        }

        Expr::Call { name, args } => {
            let mut evaluated_args = Vec::new();
            for arg in args {
                evaluated_args.push(eval_expr(arg, env)?);
            }
            call_function(name, evaluated_args, env, 0)
        }

        Expr::Index { object, index } => {
            let obj = eval_expr(object, env)?;
            let idx = eval_expr(index, env)?;
            match (&obj, &idx) {
                (Value::List(list), Value::Num(n)) => {
                    let i = *n as usize;
                    if i >= list.len() {
                        Err(err(format!("list index {} out of bounds (length {})", i, list.len()), 0))
                    } else {
                        Ok(list[i].clone())
                    }
                }
                (Value::Dict(entries), Value::Str(key)) => {
                    for (k, v) in entries {
                        if k == key {
                            return Ok(v.clone());
                        }
                    }
                    Err(err(format!("key '{}' not found in dict", key), 0))
                }
                (Value::Str(s), Value::Num(n)) => {
                    let i = *n as usize;
                    if i >= s.len() {
                        Err(err(format!("string index {} out of bounds (length {})", i, s.len()), 0))
                    } else {
                        Ok(Value::Str(s.chars().nth(i).unwrap().to_string()))
                    }
                }
                _ => Err(err("invalid index operation", 0)),
            }
        }

        Expr::List(elements) => {
            let mut vals = Vec::new();
            for e in elements {
                vals.push(eval_expr(e, env)?);
            }
            Ok(Value::List(vals))
        }

        Expr::Dict(entries) => {
            let mut vals = Vec::new();
            for (key_expr, val_expr) in entries {
                let key = match eval_expr(key_expr, env)? {
                    Value::Str(s) => s,
                    other => other.to_sam_string(),
                };
                let val = eval_expr(val_expr, env)?;
                vals.push((key, val));
            }
            Ok(Value::Dict(vals))
        }
    }
}

fn values_equal(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Num(x), Value::Num(y)) => x == y,
        (Value::Str(x), Value::Str(y)) => x == y,
        (Value::Bool(x), Value::Bool(y)) => x == y,
        (Value::None, Value::None) => true,
        (Value::List(x), Value::List(y)) => {
            if x.len() != y.len() {
                return false;
            }
            x.iter().zip(y.iter()).all(|(a, b)| values_equal(a, b))
        }
        _ => false,
    }
}

fn type_name(v: &Value) -> &'static str {
    match v {
        Value::Num(_) => "number",
        Value::Str(_) => "string",
        Value::Bool(_) => "bool",
        Value::None => "none",
        Value::List(_) => "list",
        Value::Dict(_) => "dict",
    }
}

fn call_function(name: &str, args: Vec<Value>, env: &mut Env, line: usize) -> Result<Value, Signal> {
    // --- Built-in functions ---
    match name {
        "print" => {
            if args.len() != 1 {
                return Err(err("print() takes exactly 1 argument", line));
            }
            println!("{}", args[0].to_sam_string());
            return Ok(Value::None);
        }
        "str" => {
            if args.len() != 1 {
                return Err(err("str() takes exactly 1 argument", line));
            }
            return Ok(Value::Str(args[0].to_sam_string()));
        }
        "len" => {
            if args.len() != 1 {
                return Err(err("len() takes exactly 1 argument", line));
            }
            match &args[0] {
                Value::Str(s) => return Ok(Value::Num(s.len() as f64)),
                Value::List(l) => return Ok(Value::Num(l.len() as f64)),
                Value::Dict(d) => return Ok(Value::Num(d.len() as f64)),
                _ => return Err(err("len() requires a string, list, or dict", line)),
            }
        }
        "type" => {
            if args.len() != 1 {
                return Err(err("type() takes exactly 1 argument", line));
            }
            return Ok(Value::Str(type_name(&args[0]).to_string()));
        }
        "num" => {
            if args.len() != 1 {
                return Err(err("num() takes exactly 1 argument", line));
            }
            match &args[0] {
                Value::Str(s) => match s.parse::<f64>() {
                    Ok(n) => return Ok(Value::Num(n)),
                    Err(_) => return Err(err(format!("cannot convert '{}' to number", s), line)),
                },
                Value::Num(n) => return Ok(Value::Num(*n)),
                _ => return Err(err("num() requires a string or number", line)),
            }
        }
        "assert" => {
            if args.is_empty() || args.len() > 2 {
                return Err(err("assert() takes 1 or 2 arguments", line));
            }
            if !args[0].is_truthy() {
                let msg = if args.len() == 2 {
                    args[1].to_sam_string()
                } else {
                    "assertion failed".to_string()
                };
                eprintln!("assertion error: {}", msg);
                process::exit(1);
            }
            return Ok(Value::None);
        }
        "input" => {
            let mut line_buf = String::new();
            std::io::stdin().read_line(&mut line_buf).unwrap_or(0);
            // Remove trailing newline
            if line_buf.ends_with('\n') {
                line_buf.pop();
                if line_buf.ends_with('\r') {
                    line_buf.pop();
                }
            }
            return Ok(Value::Str(line_buf));
        }
        _ => {}
    }

    // --- User-defined functions ---
    let func = match env.functions.get(name) {
        Some(f) => f.clone(),
        None => return Err(err(format!("undefined function '{}'", name), line)),
    };

    // Validate argument count
    let min_params = func.params.iter().filter(|p| p.default.is_none()).count();
    let max_params = func.params.len();
    if args.len() < min_params || args.len() > max_params {
        return Err(err(
            format!(
                "function '{}' expects {} to {} arguments, got {}",
                name, min_params, max_params, args.len()
            ),
            line,
        ));
    }

    env.push_scope();
    env.call_stack.push(name.to_string());

    // Bind parameters
    for (i, param) in func.params.iter().enumerate() {
        let value = if i < args.len() {
            args[i].clone()
        } else {
            // Use default value
            match &param.default {
                Some(default_expr) => eval_expr(default_expr, env)?,
                None => return Err(err(format!("missing argument '{}'", param.name), line)),
            }
        };
        env.declare(&param.name, value, false);
    }

    // Execute body
    let result = exec_block(&func.body, env);

    env.call_stack.pop();
    env.pop_scope();

    match result {
        Ok(val) => Ok(val),
        Err(Signal::Return(val)) => Ok(val),
        Err(other) => Err(other),
    }
}

fn exec_block(stmts: &[Stmt], env: &mut Env) -> Result<Value, Signal> {
    let mut last = Value::None;
    for stmt in stmts {
        last = exec_stmt(stmt, env)?;
    }
    Ok(last)
}

fn exec_stmt(stmt: &Stmt, env: &mut Env) -> Result<Value, Signal> {
    match stmt {
        Stmt::Let { name, value } => {
            let val = eval_expr(value, env)?;
            env.declare(name, val, false);
            Ok(Value::None)
        }

        Stmt::Const { name, value } => {
            let val = eval_expr(value, env)?;
            env.declare(name, val, true);
            Ok(Value::None)
        }

        Stmt::Assign { name, value } => {
            let val = eval_expr(value, env)?;
            env.set(name, val).map_err(|msg| err(msg, 0))?;
            Ok(Value::None)
        }

        Stmt::IndexAssign { object, index, value } => {
            let idx = eval_expr(index, env)?;
            let val = eval_expr(value, env)?;

            // We need the variable name to mutate it in place
            // The object expression should be a Var
            match object {
                Expr::Var(var_name) => {
                    let mut obj = env.get(var_name).ok_or_else(|| {
                        err(format!("undefined variable '{}'", var_name), 0)
                    })?;
                    match (&mut obj, &idx) {
                        (Value::List(ref mut list), Value::Num(n)) => {
                            let i = *n as usize;
                            if i == list.len() {
                                // Append
                                list.push(val);
                            } else if i < list.len() {
                                list[i] = val;
                            } else {
                                return Err(err(
                                    format!("list index {} out of bounds (length {})", i, list.len()),
                                    0,
                                ));
                            }
                        }
                        (Value::Dict(ref mut entries), Value::Str(key)) => {
                            // Update existing key or add new one
                            for (k, v) in entries.iter_mut() {
                                if k == key {
                                    *v = val;
                                    env.set(var_name, obj)
                                        .map_err(|msg| err(msg, 0))?;
                                    return Ok(Value::None);
                                }
                            }
                            entries.push((key.clone(), val));
                        }
                        _ => return Err(err("invalid index assignment", 0)),
                    }
                    env.set(var_name, obj).map_err(|msg| err(msg, 0))?;
                }
                _ => return Err(err("index assignment target must be a variable", 0)),
            }
            Ok(Value::None)
        }

        Stmt::CompoundAssign { name, op, value } => {
            let current = env.get(name).ok_or_else(|| {
                err(format!("undefined variable '{}'", name), 0)
            })?;
            let rhs = eval_expr(value, env)?;

            let new_val = match op {
                BinOp::Add => match (&current, &rhs) {
                    (Value::Num(a), Value::Num(b)) => Value::Num(a + b),
                    (Value::Str(a), Value::Str(b)) => Value::Str(format!("{}{}", a, b)),
                    _ => return Err(err("invalid types for +=", 0)),
                },
                BinOp::Sub => match (&current, &rhs) {
                    (Value::Num(a), Value::Num(b)) => Value::Num(a - b),
                    _ => return Err(err("subtraction requires numbers", 0)),
                },
                BinOp::Mul => match (&current, &rhs) {
                    (Value::Num(a), Value::Num(b)) => Value::Num(a * b),
                    _ => return Err(err("multiplication requires numbers", 0)),
                },
                BinOp::Div => match (&current, &rhs) {
                    (Value::Num(a), Value::Num(b)) => {
                        if *b == 0.0 {
                            return Err(err("division by zero", 0));
                        }
                        Value::Num(a / b)
                    }
                    _ => return Err(err("division requires numbers", 0)),
                },
                BinOp::Mod => match (&current, &rhs) {
                    (Value::Num(a), Value::Num(b)) => {
                        if *b == 0.0 {
                            return Err(err("modulo by zero", 0));
                        }
                        Value::Num(a % b)
                    }
                    _ => return Err(err("modulo requires numbers", 0)),
                },
                _ => return Err(err(format!("unsupported compound assignment operator"), 0)),
            };

            env.set(name, new_val).map_err(|msg| err(msg, 0))?;
            Ok(Value::None)
        }

        Stmt::If { cond, body, else_ifs, else_body } => {
            let cond_val = eval_expr(cond, env)?;
            if cond_val.is_truthy() {
                env.push_scope();
                let result = exec_block(body, env);
                env.pop_scope();
                return result;
            }
            for (elif_cond, elif_body) in else_ifs {
                let elif_val = eval_expr(elif_cond, env)?;
                if elif_val.is_truthy() {
                    env.push_scope();
                    let result = exec_block(elif_body, env);
                    env.pop_scope();
                    return result;
                }
            }
            if let Some(else_stmts) = else_body {
                env.push_scope();
                let result = exec_block(else_stmts, env);
                env.pop_scope();
                return result;
            }
            Ok(Value::None)
        }

        Stmt::Loop(body) => {
            loop {
                env.push_scope();
                let result = exec_block(body, env);
                env.pop_scope();
                match result {
                    Ok(_) => continue,
                    Err(Signal::Continue) => continue,
                    Err(Signal::Break) => break,
                    Err(other) => return Err(other),
                }
            }
            Ok(Value::None)
        }

        Stmt::Break => Err(Signal::Break),
        Stmt::Continue => Err(Signal::Continue),

        Stmt::Return(expr_opt) => {
            let val = match expr_opt {
                Some(e) => eval_expr(e, env)?,
                None => Value::None,
            };
            Err(Signal::Return(val))
        }

        Stmt::Expr(expr) => {
            eval_expr(expr, env)?;
            Ok(Value::None)
        }
    }
}

fn interpret(program: &Program) -> Result<(), String> {
    let mut env = Env::new();
    env.register_functions(program);

    // Find and call main
    if !env.functions.contains_key("main") {
        return Err("no 'main' function defined".to_string());
    }

    match call_function("main", vec![], &mut env, 0) {
        Ok(_) => Ok(()),
        Err(Signal::Error(e)) => {
            Err(format!("runtime error at line {}: {}\nstack trace:\n{}",
                e.line, e.msg, env.stack_trace()))
        }
        Err(Signal::Break) => Err("break outside of loop".to_string()),
        Err(Signal::Continue) => Err("continue outside of loop".to_string()),
        Err(Signal::Return(_)) => Ok(()), // return from main is fine
    }
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

#[derive(ClapParser)]
#[command(name = "samscript")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run a SamScript program
    Run {
        /// Path to .sam file
        file: String,
    },
    /// Compile a SamScript program
    Compile {
        /// Path to .sam file
        file: String,
        /// Output file path
        #[arg(short, long)]
        o: String,
        /// Target triple
        #[arg(long)]
        target: String,
    },
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Run { file } => {
            let source = match fs::read_to_string(&file) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("error: could not read '{}': {}", file, e);
                    process::exit(1);
                }
            };

            let tokens = match tokenize(&source) {
                Ok(t) => t,
                Err(e) => {
                    eprintln!("lexer error at line {}: {}", e.line, e.msg);
                    process::exit(1);
                }
            };

            let program = match parse(tokens) {
                Ok(p) => p,
                Err(e) => {
                    eprintln!("parse error at line {}: {}", e.line, e.msg);
                    process::exit(1);
                }
            };

            if let Err(e) = interpret(&program) {
                eprintln!("{}", e);
                process::exit(1);
            }
        }
        Commands::Compile { file: _, o: _, target: _ } => {
            eprintln!("error: WASM compilation not yet implemented");
            process::exit(1);
        }
    }
}
