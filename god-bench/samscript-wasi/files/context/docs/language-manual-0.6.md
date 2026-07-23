# SamScript Language Manual 0.6

Document state: archived distribution manual

Published: 2024-08-02

This manual describes the desktop 0.6 interpreter. It is retained because its
examples are useful lexer and parser inputs. It does not describe the released
WASI target. In particular, its integer model, function lookup, scoping, and
failure conventions conflict with later releases.

## 1. Source units

A source unit was decoded as UTF-8 and split into physical lines before token
recognition. A carriage return immediately before newline was discarded. The
scanner treated a newline as a statement boundary unless it occurred between
parentheses. Braces were tokens but did not suppress newline boundaries. This
made the following legal only when the continuation began inside the call:

```sam
print(
    add(20, 22)
)
```

Comments began with `//`. The 0.6 scanner removed comments before scanning
quotes, which was a known bug: `"https://example"` was truncated. The test
suite worked around the defect by constructing such strings with
concatenation. Block comments were proposed but never shipped.

Identifiers were documented as letters followed by letters or digits. The
implementation also accepted underscore, Latin-1 letters, and bytes above
127. Names were case-sensitive. Keywords were recognized after locale-aware
lowercasing, so a Turkish locale could alter tokenization. Build images pinned
the C locale rather than fixing the scanner.

## 2. Values in the desktop interpreter

Version 0.6 had five runtime tags: integer, decimal, text, flag, and empty.
Integer literals used signed 63-bit storage with one tag bit. A literal with a
decimal point used the host `long double`; serialized bytecode narrowed that
value to a 64-bit double. Arithmetic selected a result tag from both operands.
Integer addition, subtraction, and multiplication trapped on overflow.
Division of two integers truncated toward zero, while either decimal operand
selected floating division.

The literal `none` produced empty. Empty formatted as an empty string, not as
the word `none`. Flags formatted as `yes` and `no`. Number formatting was
locale-sensitive and used six fractional digits unless the program called the
format package. These details explain many old golden files and are not safe
guidance for newer runtimes.

Text values were reference-counted byte strings. Most operations did not
validate UTF-8 after slicing. `len(text)` returned bytes. Concatenation accepted
only two text values and did not coerce numbers. The lexer recognized `\n`,
`\r`, `\t`, `\\`, and `\"`; unknown escapes silently dropped the backslash.
Dollar had no special role because interpolation was not yet implemented.

## 3. Expressions

The handwritten parser used the following archived precedence table, from low
to high:

1. `and` and `or` at the same precedence
2. all six comparisons at the same precedence
3. `+` and `-`
4. `*`, `/`, and `%`
5. unary `not` and unary `-`
6. `**`
7. calls

Every binary operator, including power, associated left. Thus `2 ** 3 ** 2`
was read as `(2 ** 3) ** 2`. Comparison chains were ordinary left-associated
binary operations. Because comparisons returned flags and flags coerced to
integers, `1 < 2 < 3` happened to produce `yes`.

`and` and `or` evaluated both operands before applying their operator. The VM
encoded them as ordinary binary instructions. They accepted flags and
integers, with zero considered false. Their result was always a flag. A common
idiom deliberately relied on the right operand running:

```sam
ready and record_attempt()
```

Assignments were expressions and returned the assigned value. Chained
assignment was therefore permitted. Compound assignment expanded in the
parser and could evaluate an indexed left side twice. The desktop optimizer
also folded arithmetic before overflow checks, producing differences between
debug and optimized bytecode.

## 4. Declarations and scope

Both `let` and `const` created mutable function locals. The distinction was
reserved for a future static checker. A declaration allocated a numbered slot
when the function was parsed. A block did not create a scope; declaring the
same name in a nested branch reused the existing slot. A declaration in an
unexecuted branch still made its slot visible elsewhere with the empty value.

Functions used dynamic scope for unresolved names. A callee first searched its
parameters and locals, then walked active caller frames. This allowed small
configuration helpers but prevented independent compilation. Top-level
functions became visible in source order. Calling a later declaration failed
unless an earlier declaration with that name had already been installed.

The following example printed `41` and then `42` in 0.6 because `bump` mutated
the caller's local through dynamic lookup:

```sam
fn bump() {
    value += 1
    print(value)
}

fn main() {
    let value = 40
    bump()
    value += 1
    print(value)
}
```

Parameters were assigned left to right. Too few arguments filled remaining
slots with empty. Extra arguments were retained in an implicit `arguments`
list. Defaults were evaluated once when the declaration was installed, not at
each call. Recursive calls were capped at 128 frames by the desktop VM.

## 5. Statements and control transfer

The conditional syntax already required braces. Conditions accepted flags,
integers, text, and empty. Empty text, integer zero, and empty were false.
`else if` was parsed as an `else` containing another conditional, so debugger
line tables showed an additional synthetic frame.

The only loop statement was `loop`. A loop condition could optionally appear
after the keyword in 0.6, although this extension was omitted from most
examples:

```sam
loop index < limit {
    index += 1
}
```

`break` exited the nearest loop. `continue` jumped directly to the loop header.
The bytecode verifier did not reject either statement outside a loop; the VM
then treated it as a function return. A bare return produced empty. Returning
from `main` did not set the process status.

## 6. Text templates proposal

The 0.6.4 design addendum proposed `$name` replacement and `$(expression)`
replacement. Replacement was to happen in a post-lexing pass. Nested calls in
templates were forbidden because the pass stopped at the first close
parenthesis. Escaped dollar used `$$`. None of this proposal shipped in the
desktop interpreter, but prototype compiler branches contain partial support.

The proposed renderer converted empty to an empty field, flags to `yes` or
`no`, integers to decimal, and decimals with six digits. It allocated one
buffer based on a rough length estimate and retried on overflow. Reviewers
rejected the design because embedded expressions had no source spans and
because retrying repeated side effects.

## 7. Built-in library

The core desktop builtins were `say`, `read`, `size`, `kind`, `text`, `number`,
`check`, and `load`. Compatibility aliases provided `print`, `input`, `len`,
`type`, `str`, `num`, `assert`, and `read_file`. `say` wrote to the process
console through buffered stdio and flushed only when the buffer filled or the
program ended. A failed `check` wrote to stdout and aborted.

`number(text)` accepted leading whitespace, a numeric prefix, and ignored the
remaining suffix. `size(text)` counted bytes. `kind(empty)` returned `nil`.
The filesystem API resolved paths relative to the process working directory,
not the importing source file. The desktop shell exposed environment and
process builtins that were never intended for sandbox use.

## 8. Modules

An import searched the current directory, `SAM_PATH`, and a user installation
directory. Imports executed their module immediately and copied selected
globals into the caller. The cache key was the literal import spelling, so
different relative spellings could execute one file more than once. Cycles
eventually reached the VM frame limit instead of receiving a dedicated error.

Module initialization order depended on source order. A failed import left a
partially initialized cache entry. Subsequent imports could observe functions
defined before the failure. This behavior was considered useful for the
interactive shell and disastrous for reproducible builds.

## 9. Bytecode and diagnostics

The `.sbc` format began with `SAM6`, a native-endian word count, a string
table, and function records. Instructions were one-byte opcodes followed by
native-endian operands. Files were not portable between 32-bit and 64-bit
hosts. Debug tables stored only physical line numbers.

Compile errors printed `file(line): message` to stdout and returned status 2.
Runtime errors printed the current function and message, also to stdout, then
returned status 70. Division by integer zero used the text `arithmetic fault`;
floating division followed host behavior and could produce infinity. Missing
names used `slot not initialized`, even if the slot did not exist.

The interactive shell recovered after an error by discarding frames but
retaining module globals. Batch mode aborted. Stack traces were available only
when `SAM_TRACE=1` was set and listed instruction offsets rather than source
columns.

## 10. Porting checklist from the archive

The original checklist below was written for desktop embedders. It is useful
history, not a current conformance list.

- Pin locale before tokenizing or formatting.
- Reject bytecode with a pointer width different from the host.
- Set the desired 0.6 recursion cap before executing untrusted plugins.
- Expect dynamic lookup to cross caller frames.
- Do not assume `const` is immutable.
- Remember that both logical operands execute.
- Preserve left-associated power when reproducing old saved calculations.
- Translate status 70 into the embedding application's generic script error.
- Flush `say` before handing control back to a graphical event loop.
- Canonicalize module paths if duplicate initialization is undesirable.

The 0.7 planning branch attempted to remove most of these behaviors. Saved 0.6
programs were not promised source compatibility, and no migration profile was
defined for WebAssembly.
