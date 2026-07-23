# Reference interpreter implementation notes

Component: tree-walk interpreter

Snapshot: commit `4f6a92d`, between language 0.9 and 1.0

Role: behavioral comparison aid, not an ABI specification.

## Front end

The lexer emits a newline token after nonblank source lines. Parsers call
`skip_newlines` around braces, so line breaks are generally statement
separators rather than expression whitespace. Comments consume characters up
to but not including the newline.

Numeric scanning accepts decimal digits and one fractional part. A dot is
part of a number only when followed by a digit; this distinction allows the
two-dot token to be recognized after an integer. The scanner stores parsed
numbers in the host's `f64`.

Strings preserve ordinary characters and decode newline, tab, backslash,
quote, and escaped dollar. On `${`, the lexer balances braces and sends the
captured text through a nested expression parser. Source line accounting
continues inside the capture.

The token set in this snapshot includes:

```text
Num Str InterpStr True False NoneLit Ident
Fn Let Const If Else Loop Break Continue Return
From Import And Or Not
Plus Minus Star Slash Percent StarStar DotDot
EqEq BangEq Lt Gt LtEq GtEq Eq
PlusEq MinusEq StarEq SlashEq PercentEq
LParen RParen LBrace RBrace LBracket RBracket
Comma Colon Arrow Newline Eof
```

The parser represents interpolation as alternating literal and expression
nodes. It does not lower interpolation to concatenation until evaluation.
Exponentiation recurses on its right operand, while multiplication and
addition use loops over operators and are left-associative.

## Runtime values

The interpreter snapshot has number, string, bool, none, list, and dictionary
values. Dictionary keys are converted to a stable key representation before
lookup. Functions are declarations stored separately from ordinary values.

The display helper first tests whether a number has zero fractional part. If
so, it asks the host formatter for integer-style output; otherwise it uses the
host's default shortest display. This behavior depends on Rust's formatter and
was one reason the compiler contract later wrote the formatting rule down.

Strings are Rust UTF-8 strings. Current indexing code walks Unicode scalar
values, but an older fast path indexed bytes. Tests mentioning non-ASCII
indexing were disabled while that difference was reviewed.

## Environments

An environment owns a vector of scopes. Entering a brace block pushes an
empty scope and leaving it pops that scope. Declaration checks only the current
scope, permitting deliberate shadowing.

Lookup walks scopes from inner to outer. Assignment in this snapshot also
walks outward and updates the first mutable binding it finds. A design note in
the archived language document says inner scopes cannot assign outward; that
note did not match this implementation and was not automatically promoted to
the compiler release.

Each binding carries an immutable bit. Compound assignment performs lookup,
computes a new value, then uses the same assignment path, so constants reject
both ordinary and compound writes.

Calls build a new function environment. Parameters are inserted in order.
When an argument is absent, the default expression is evaluated after earlier
parameters exist. Too many arguments produce an arity error.

## Control signals

Statement evaluation returns one of four internal signals: normal, return,
break, or continue. A block propagates any non-normal signal after releasing
its scope. A loop consumes break and continue but propagates return.

Condition evaluation uses a helper named `truthy`. At this snapshot it accepts
booleans directly and also accepts legacy numeric and string truthiness. The
WASI compiler working group considered that behavior accidental because it
survived from 0.8; consumers should consult a release contract rather than
copy the helper blindly.

Logical `and` and `or` are evaluated before the generic binary-operation
dispatcher. This gives them short-circuit behavior. Their snapshot result is
always a boolean, even when legacy truthiness accepts another input type.

## Arithmetic

Addition, subtraction, multiplication, division, modulo, and exponentiation
dispatch on pairs of numbers. Concatenation has a separate operation that
formats each side. Comparing different types is an error except equality,
which returns false.

Division checks `right == 0.0` before host division. Since positive and
negative zero compare equal, both fault. Modulo uses the same guard. The error
text includes the source line and a call-chain assembled by the evaluator.

Power calls the host `powf`, not repeated multiplication. This matters for
fractional and negative exponents, although the early compiler fixtures mostly
exercise nonnegative integral exponents.

## Builtins

`print` formats one value and writes a newline. `str` returns the same display
form. `num` trims neither leading nor trailing nonnumeric text before parsing.
`type` returns lowercase type names. `len` handles strings, lists, and maps.

The bootstrap build adds `read_file` and `args`; ordinary release builds do
not expose those names to compiled programs. `input` exists in the interpreter
but was deferred from the first WASI compiler subset.

## Modules

Import processing happens before `main` in the interpreter. It resolves paths
relative to the importing file and tracks an active set for cycle detection.
This subsystem was not included in the initial compiler milestone.

## Error transport

Interpreter errors are rich host values carrying a message and line. The CLI
prints them and exits one. WebAssembly cannot reuse this representation
directly; a compiler runtime needs a deterministic message strategy and host
termination path.

The source implementation has more language surface than every compiler
milestone. Presence here does not imply that a particular target release must
compile lists, dictionaries, modules, stdin, or indexing.
