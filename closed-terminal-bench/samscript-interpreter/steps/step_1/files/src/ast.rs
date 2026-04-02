// ast.rs — Complete AST type definitions for SamScript
//
// This file is complete. You should not need to modify it for Step 1,
// but you may extend it in later steps (e.g. adding list/dict types).

/// A complete SamScript program: a series of top-level function declarations
/// and import statements.
#[derive(Debug, Clone)]
pub struct Program {
    pub functions: Vec<FnDecl>,
    pub imports: Vec<ImportDecl>,
}

/// An import declaration: `from <module> import <names>`
#[derive(Debug, Clone)]
pub struct ImportDecl {
    pub module: String,
    pub names: Vec<String>,
    pub line: usize,
}

/// A function declaration with optional parameter defaults and return type hint.
#[derive(Debug, Clone)]
pub struct FnDecl {
    pub name: String,
    pub params: Vec<Param>,
    pub return_type: Option<String>,
    pub body: Vec<Stmt>,
    pub line: usize,
}

/// A function parameter with optional type hint and default value.
#[derive(Debug, Clone)]
pub struct Param {
    pub name: String,
    pub type_hint: Option<String>,
    pub default: Option<Expr>,
}

/// Statements that can appear inside a function body.
#[derive(Debug, Clone)]
pub enum Stmt {
    /// `let name = expr`
    Let {
        name: String,
        value: Expr,
        line: usize,
    },
    /// `const name = expr`
    Const {
        name: String,
        value: Expr,
        line: usize,
    },
    /// Assignment: `target = expr` or `target += expr` etc.
    Assign {
        target: AssignTarget,
        op: AssignOp,
        value: Expr,
        line: usize,
    },
    /// Bare expression statement (e.g. function call)
    Expr {
        expr: Expr,
        line: usize,
    },
    /// `if cond { ... } else if cond { ... } else { ... }`
    If {
        condition: Expr,
        then_body: Vec<Stmt>,
        else_if_branches: Vec<(Expr, Vec<Stmt>)>,
        else_body: Option<Vec<Stmt>>,
        line: usize,
    },
    /// `loop { ... }`
    Loop {
        body: Vec<Stmt>,
        line: usize,
    },
    /// `break`
    Break { line: usize },
    /// `continue`
    Continue { line: usize },
    /// `return` or `return expr`
    Return {
        value: Option<Expr>,
        line: usize,
    },
    /// `from module import name1, name2`
    Import {
        module: String,
        names: Vec<String>,
        line: usize,
    },
}

/// The left-hand side of an assignment.
#[derive(Debug, Clone)]
pub enum AssignTarget {
    /// Simple variable: `x = ...`
    Ident(String),
    /// Indexed access: `a[i] = ...`
    Index(Box<Expr>, Box<Expr>),
    /// Field access: `a.field = ...`
    Field(Box<Expr>, String),
}

/// Assignment operators.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum AssignOp {
    /// `=`
    Eq,
    /// `+=`
    AddEq,
    /// `-=`
    SubEq,
    /// `*=`
    MulEq,
    /// `/=`
    DivEq,
    /// `%=`
    ModEq,
}

/// Expressions.
#[derive(Debug, Clone)]
pub enum Expr {
    /// A literal value
    Literal(Literal),
    /// A variable reference
    Ident(String),
    /// Binary operation: `left op right`
    BinOp {
        op: BinOp,
        left: Box<Expr>,
        right: Box<Expr>,
    },
    /// Unary operation: `op operand`
    UnaryOp {
        op: UnaryOp,
        operand: Box<Expr>,
    },
    /// Function call: `func(args...)`
    Call {
        function: Box<Expr>,
        args: Vec<Expr>,
    },
    /// Index access: `object[index]`
    Index {
        object: Box<Expr>,
        index: Box<Expr>,
    },
    /// Field/method access: `object.field`
    FieldAccess {
        object: Box<Expr>,
        field: String,
    },
    /// String interpolation: `"text ${expr} more text"`
    StringInterp {
        parts: Vec<StringPart>,
    },
    /// List literal: `[a, b, c]`
    ListLiteral {
        elements: Vec<Expr>,
    },
    /// Dict literal: `{key: value, ...}`
    DictLiteral {
        entries: Vec<(Expr, Expr)>,
    },
}

/// A piece of an interpolated string.
#[derive(Debug, Clone)]
pub enum StringPart {
    /// Raw text between interpolations
    Lit(String),
    /// An interpolated expression: `${expr}`
    Expr(Expr),
}

/// Literal values.
#[derive(Debug, Clone)]
pub enum Literal {
    /// Floating-point number (all numbers are f64)
    Number(f64),
    /// String literal
    Str(String),
    /// Boolean: `true` or `false`
    Bool(bool),
    /// The `none` value
    None,
}

/// Binary operators, ordered by precedence (low to high in the parser).
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum BinOp {
    // Logical (lowest precedence)
    Or,
    And,
    // Comparison
    Eq,
    Neq,
    Lt,
    Gt,
    Le,
    Ge,
    // String concatenation
    Concat,
    // Arithmetic
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    // Exponentiation (highest precedence)
    Pow,
}

/// Unary operators.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum UnaryOp {
    /// Arithmetic negation: `-x`
    Neg,
    /// Logical negation: `not x`
    Not,
}
