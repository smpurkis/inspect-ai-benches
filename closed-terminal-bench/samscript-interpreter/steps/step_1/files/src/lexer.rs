// lexer.rs — Tokenizer for SamScript
//
// STATUS: ~60% complete. Basic structure and some token types are implemented.
// YOU MUST complete:
//   - String interpolation tokenizing (handle `${}` inside strings)
//   - Multi-character operators: >=, <=, !=, **, +=, -=, *=, /=, %=, ==
//   - Keyword recognition for: and, or, not, loop, break, continue, const,
//     from, import, none, true, false
//   - Arrow return type annotation: ->
//   - Proper line tracking across multi-line strings

/// Token types produced by the lexer.
#[derive(Debug, Clone, PartialEq)]
pub enum Token {
    // Literals
    Number(f64),
    StringLit(String),
    /// An interpolated string is broken into parts: literal text and expressions.
    /// The lexer emits InterpStart, then alternating StringFragment / InterpExpr tokens,
    /// then InterpEnd.
    InterpStart,
    StringFragment(String),
    InterpExprStart,  // marks the beginning of ${
    InterpExprEnd,    // marks the closing }
    InterpEnd,

    // Identifiers and keywords
    Ident(String),
    Fn,
    Let,
    Const,
    If,
    Else,
    Loop,
    Break,
    Continue,
    Return,
    From,
    Import,
    And,
    Or,
    Not,
    True,
    False,
    None,

    // Operators
    Plus,       // +
    Minus,      // -
    Star,       // *
    Slash,      // /
    Percent,    // %
    StarStar,   // **
    Eq,         // =
    EqEq,       // ==
    BangEq,     // !=
    Lt,         // <
    Gt,         // >
    LtEq,       // <=
    GtEq,       // >=
