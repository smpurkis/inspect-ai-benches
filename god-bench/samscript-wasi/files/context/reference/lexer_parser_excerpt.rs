//! Extract from the 0.9 interpreter front end.
//!
//! Retained because the compiler and interpreter share surface syntax. This
//! snapshot is implementation evidence, not a target or runtime contract.

#[derive(Clone, Debug, PartialEq)]
enum TokenKind {
    Number(f64),
    String(String),
    Interpolation(Vec<StringPart>),
    Identifier(String),
    Fn,
    Let,
    Const,
    If,
    Else,
    Loop,
    Break,
    Continue,
    Return,
    And,
    Or,
    Not,
    True,
    False,
    None,
    Plus,
    Minus,
    Star,
    Slash,
    Percent,
    Power,
    Concat,
    Equal,
    NotEqual,
    Less,
    Greater,
    LessEqual,
    GreaterEqual,
    Assign,
    PlusAssign,
    MinusAssign,
    StarAssign,
    SlashAssign,
    PercentAssign,
    LeftParen,
    RightParen,
    LeftBrace,
    RightBrace,
    Comma,
    Newline,
    Eof,
}

#[derive(Clone, Debug, PartialEq)]
enum StringPart {
    Literal(String),
    Expression(String),
}

#[derive(Clone, Debug)]
struct Token {
    kind: TokenKind,
    line: usize,
}

fn scan(source: &str) -> Result<Vec<Token>, String> {
    let chars: Vec<char> = source.chars().collect();
    let mut tokens = Vec::new();
    let mut cursor = 0;
    let mut line = 1;

    while cursor < chars.len() {
        let current = chars[cursor];
        if matches!(current, ' ' | '\t' | '\r') {
            cursor += 1;
            continue;
        }
        if current == '\n' {
            if !matches!(tokens.last(), None | Some(Token { kind: TokenKind::Newline, .. })) {
                tokens.push(Token { kind: TokenKind::Newline, line });
            }
            cursor += 1;
            line += 1;
            continue;
        }
        if current == '/' && chars.get(cursor + 1) == Some(&'/') {
            cursor += 2;
            while chars.get(cursor).is_some_and(|ch| *ch != '\n') {
                cursor += 1;
            }
            continue;
        }
        if current.is_ascii_digit() {
            let start = cursor;
            while chars.get(cursor).is_some_and(char::is_ascii_digit) {
                cursor += 1;
            }
            if chars.get(cursor) == Some(&'.')
                && chars.get(cursor + 1).is_some_and(char::is_ascii_digit)
            {
                cursor += 1;
                while chars.get(cursor).is_some_and(char::is_ascii_digit) {
                    cursor += 1;
                }
            }
            let text: String = chars[start..cursor].iter().collect();
            let value = text.parse().map_err(|_| format!("invalid number at {line}"))?;
            tokens.push(Token { kind: TokenKind::Number(value), line });
            continue;
        }
        if current == '"' {
            let start_line = line;
            cursor += 1;
            let mut parts = Vec::new();
            let mut literal = String::new();
            let mut interpolated = false;
            while cursor < chars.len() && chars[cursor] != '"' {
                match chars[cursor] {
                    '\\' => {
                        cursor += 1;
                        let escaped = *chars.get(cursor)
                            .ok_or_else(|| format!("unterminated escape at {start_line}"))?;
                        match escaped {
                            'n' => literal.push('\n'),
                            't' => literal.push('\t'),
                            '\\' => literal.push('\\'),
                            '"' => literal.push('"'),
                            '$' => literal.push('$'),
                            other => {
                                literal.push('\\');
                                literal.push(other);
                            }
                        }
                        cursor += 1;
                    }
                    '$' if chars.get(cursor + 1) == Some(&'{') => {
                        interpolated = true;
                        if !literal.is_empty() {
                            parts.push(StringPart::Literal(std::mem::take(&mut literal)));
                        }
                        cursor += 2;
                        let mut depth = 1;
                        let mut expression = String::new();
                        while cursor < chars.len() && depth > 0 {
                            match chars[cursor] {
                                '{' => {
                                    depth += 1;
                                    expression.push('{');
                                }
                                '}' => {
                                    depth -= 1;
                                    if depth > 0 {
                                        expression.push('}');
                                    }
                                }
                                '\n' => {
                                    line += 1;
                                    expression.push('\n');
                                }
                                ch => expression.push(ch),
                            }
                            cursor += 1;
                        }
                        if depth != 0 {
                            return Err(format!("unterminated interpolation at {start_line}"));
                        }
                        parts.push(StringPart::Expression(expression));
                    }
                    '\n' => {
                        line += 1;
                        literal.push('\n');
                        cursor += 1;
                    }
                    ch => {
                        literal.push(ch);
                        cursor += 1;
                    }
                }
            }
            if chars.get(cursor) != Some(&'"') {
                return Err(format!("unterminated string at {start_line}"));
            }
            cursor += 1;
            let kind = if interpolated {
                if !literal.is_empty() {
                    parts.push(StringPart::Literal(literal));
                }
                TokenKind::Interpolation(parts)
            } else {
                TokenKind::String(literal)
            };
            tokens.push(Token { kind, line: start_line });
            continue;
        }
        if current.is_ascii_alphabetic() || current == '_' {
            let start = cursor;
            cursor += 1;
            while chars.get(cursor).is_some_and(|ch| ch.is_ascii_alphanumeric() || *ch == '_') {
                cursor += 1;
            }
            let word: String = chars[start..cursor].iter().collect();
            let kind = match word.as_str() {
                "fn" => TokenKind::Fn,
                "let" => TokenKind::Let,
                "const" => TokenKind::Const,
                "if" => TokenKind::If,
                "else" => TokenKind::Else,
                "loop" => TokenKind::Loop,
                "break" => TokenKind::Break,
                "continue" => TokenKind::Continue,
                "return" => TokenKind::Return,
                "and" => TokenKind::And,
                "or" => TokenKind::Or,
                "not" => TokenKind::Not,
                "true" => TokenKind::True,
                "false" => TokenKind::False,
                "none" => TokenKind::None,
                _ => TokenKind::Identifier(word),
            };
            tokens.push(Token { kind, line });
            continue;
        }

        let pair = chars.get(cursor + 1).map(|next| (current, *next));
        let double = match pair {
            Some(('*', '*')) => Some(TokenKind::Power),
            Some(('.', '.')) => Some(TokenKind::Concat),
            Some(('=', '=')) => Some(TokenKind::Equal),
            Some(('!', '=')) => Some(TokenKind::NotEqual),
            Some(('<', '=')) => Some(TokenKind::LessEqual),
            Some(('>', '=')) => Some(TokenKind::GreaterEqual),
            Some(('+', '=')) => Some(TokenKind::PlusAssign),
            Some(('-', '=')) => Some(TokenKind::MinusAssign),
            Some(('*', '=')) => Some(TokenKind::StarAssign),
            Some(('/', '=')) => Some(TokenKind::SlashAssign),
            Some(('%', '=')) => Some(TokenKind::PercentAssign),
            _ => None,
        };
        if let Some(kind) = double {
            tokens.push(Token { kind, line });
            cursor += 2;
            continue;
        }

        let kind = match current {
            '+' => TokenKind::Plus,
            '-' => TokenKind::Minus,
            '*' => TokenKind::Star,
            '/' => TokenKind::Slash,
            '%' => TokenKind::Percent,
            '<' => TokenKind::Less,
            '>' => TokenKind::Greater,
            '=' => TokenKind::Assign,
            '(' => TokenKind::LeftParen,
            ')' => TokenKind::RightParen,
            '{' => TokenKind::LeftBrace,
            '}' => TokenKind::RightBrace,
            ',' => TokenKind::Comma,
            other => return Err(format!("unexpected {other:?} at {line}")),
        };
        tokens.push(Token { kind, line });
        cursor += 1;
    }

    if matches!(tokens.last(), Some(Token { kind: TokenKind::Newline, .. })) {
        tokens.pop();
    }
    tokens.push(Token { kind: TokenKind::Eof, line });
    Ok(tokens)
}

// Precedence functions from the same snapshot. AST constructors and error
// plumbing are omitted from this excerpt, but the call order is preserved.

fn parse_expression(parser: &mut Parser) -> Result<Expr, ParseError> {
    parse_or(parser)
}

fn parse_or(parser: &mut Parser) -> Result<Expr, ParseError> {
    let mut expression = parse_and(parser)?;
    while parser.take(&TokenKind::Or) {
        expression = Expr::Binary(
            Box::new(expression),
            BinaryOperator::Or,
            Box::new(parse_and(parser)?),
        );
    }
    Ok(expression)
}

fn parse_and(parser: &mut Parser) -> Result<Expr, ParseError> {
    let mut expression = parse_equality(parser)?;
    while parser.take(&TokenKind::And) {
        expression = Expr::Binary(
            Box::new(expression),
            BinaryOperator::And,
            Box::new(parse_equality(parser)?),
        );
    }
    Ok(expression)
}

fn parse_equality(parser: &mut Parser) -> Result<Expr, ParseError> {
    let mut expression = parse_comparison(parser)?;
    loop {
        let operator = if parser.take(&TokenKind::Equal) {
            BinaryOperator::Equal
        } else if parser.take(&TokenKind::NotEqual) {
            BinaryOperator::NotEqual
        } else {
            break;
        };
        expression = Expr::Binary(
            Box::new(expression),
            operator,
            Box::new(parse_comparison(parser)?),
        );
    }
    Ok(expression)
}

fn parse_term(parser: &mut Parser) -> Result<Expr, ParseError> {
    let mut expression = parse_factor(parser)?;
    loop {
        let operator = if parser.take(&TokenKind::Plus) {
            BinaryOperator::Add
        } else if parser.take(&TokenKind::Minus) {
            BinaryOperator::Subtract
        } else if parser.take(&TokenKind::Concat) {
            BinaryOperator::Concat
        } else {
            break;
        };
        expression = Expr::Binary(
            Box::new(expression),
            operator,
            Box::new(parse_factor(parser)?),
        );
    }
    Ok(expression)
}

fn parse_power(parser: &mut Parser) -> Result<Expr, ParseError> {
    let left = parse_unary(parser)?;
    if parser.take(&TokenKind::Power) {
        return Ok(Expr::Binary(
            Box::new(left),
            BinaryOperator::Power,
            Box::new(parse_power(parser)?),
        ));
    }
    Ok(left)
}

// Parser, Expr, ParseError, and the omitted comparison/factor/unary/primary
// functions are defined in the full interpreter tree, which is not linked
// into the compiler exercise.
