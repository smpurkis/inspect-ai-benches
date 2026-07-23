# Optimizer Design Records

Repository: samc experiments

Record range: 2025-07 through 2026-02

Status: superseded meeting and decision records. These entries document why
several attractive shortcuts were rejected. A decision may be reversed by a
later entry, and none of the records is a release specification.

## ODR-11: Parse-time constant arithmetic

The parser originally constructed numeric literal nodes and immediately
reduced a binary node when both children were literals. This saved IR nodes but
lost source spans. It also made `1 / 0` a parser crash in one build and an
infinity in another, depending on whether the host operation ran before the
zero check.

Decision at the time: keep every source operator in the AST. A later local
folding pass may replace a pure subtree after type checks, while preserving the
operator span for diagnostics. Calls, assignments, and interpolation are never
pure merely because their current operands appear constant.

Rejected alternative: evaluate the entire `main` function under a fuel limit
and serialize its writes. Fuel bounds termination but does not turn execution
into compilation. It also erases mutation dependence and dynamic failures.

## ODR-14: Number representation

Three proposals competed: tagged i63/f64, f32 only, and f64 only. Tagged values
matched the desktop archive but made arithmetic branches large. f32 yielded
small WAT and matched an early GPU experiment, but numerical examples diverged
quickly. f64-only made source integer spelling a formatting concern rather
than a runtime type distinction.

The July vote chose f32 for the prototype because its benchmark was code size.
The vote was reopened after the spring simulation accumulated visible error.
By October the prototype choice had been abandoned. Old source files still use
names such as `emit_f32_add`; those names are provenance, not requirements.

## ODR-18: Scope lowering

The first compiler allocated one WebAssembly local per distinct spelling in a
function. Shadowing therefore overwrote the outer local. A stack of maps fixed
resolution during lowering, but both maps could still point to one generated
local if allocation happened before scope entry.

The revised allocator creates a binding identity for each declaration and maps
that identity to storage. Name lookup is a frontend operation. Assignment
resolves to an identity before code generation. Branch-local bindings need no
runtime destruction when represented by WebAssembly locals; they simply become
unreachable by name after lowering leaves the block.

Phi nodes were considered for values assigned in branches. Since mutable
bindings use locals, structured blocks can update the same storage directly.
The compiler only needs a merge value for expression-valued conditionals,
which were outside the prototype subset.

## ODR-21: Recursive functions

Inlining all calls simplified early output. It failed on recursion and caused
exponential code growth for helper-heavy programs. A recursion detector could
leave only cyclic calls, but then call semantics differed based on graph shape.

The selected prototype emitted one core WebAssembly function per source
function. Values used a uniform representation in each experiment. Forward
calls required a declaration pass that assigned function indices before body
lowering. The function map used ordered source appearance to preserve
deterministic indices.

Tail-call instructions were not portable enough for the engine matrix. A
self-tail-call loop transformation was sketched but postponed because default
argument evaluation and diagnostics needed precise ordering.

## ODR-24: Logical operators

An opcode mapping translated `and` to `i32.and` and `or` to `i32.or`. This was
type-correct for normalized booleans but eager. Tests using a right-hand print
made the defect obvious.

Short-circuit lowering creates a result local, a conditional block, and only
places the right expression in the selected branch. For `and`, false writes
false without evaluating right. For `or`, true writes true without evaluating
right. The right expression must itself produce a boolean; no numeric
normalization is inserted.

A later optimizer may simplify `false and X` only if it removes X rather than
hoisting X. Generic common-subexpression motion must treat calls, loads from
mutable storage, traps, and allocation as effects.

## ODR-27: Interpolation architecture

Lowering interpolation directly while parsing strings made nested braces and
quoted strings fragile. The lexer was changed to retain a sequence of literal
chunks and expression-token chunks, each with spans. The ordinary expression
parser handles each expression chunk.

Runtime lowering first converts each evaluated expression to text, sums byte
lengths with overflow checks, allocates once, and copies chunks in order. This
preserves side effects and avoids retrying expression evaluation. Literal
chunks remain UTF-8 bytes from the decoded source string.

One proposal preformatted expressions at compile time whenever they contained
only calls with literal arguments. It was rejected because function bodies can
read mutable state and because recursion makes the criterion undecidable
without a stronger effect system.

## ODR-29: Decimal rendering

Integral fast paths improve common output and avoid a trailing decimal suffix.
The fast path must first check finiteness and exact integrality. Casting an
out-of-range f64 saturates or traps differently across source languages, so the
range check precedes conversion.

Non-integral finite values need a deterministic shortest representation that
round trips to the same binary64. Linking a compact Ryu implementation was
preferred over host formatting. The generated module must perform rendering
for values computed at runtime; compiler-host Ryu is useful only for static
metadata.

The records did not settle NaN and infinity because source operations in the
required examples avoided them. Division by zero receives an explicit check
rather than producing infinity.

## ODR-31: Failure transport

Options included `unreachable`, returning an integer from `_start`, importing
an error reporter, or calling WASI process exit. Returning an integer is not
the command entry convention. Unreachable yields host-specific text and status.
An imported custom reporter breaks portable WASI.

The experiment selected a small failure helper that optionally writes a fixed
diagnostic to stderr and calls process exit. Distinct language errors can share
one process status while preserving internal error categories in compiler tests.
Compile errors never produce a runnable-looking output file.

An old branch used status 70 to mirror BSD software errors. Another used 255
because its host API accepted an unsigned byte. Those values survive in trace
archives and should not be inferred from frequency.

## ODR-34: WAT versus direct binary emission

WAT simplified development and made inspection straightforward. It requires a
trusted assembler in the build environment. Direct binary emission avoids a
subprocess but needs careful section ordering, LEB128 encoding, index spaces,
and validation.

Both routes can be deterministic. For WAT, generated symbol names, data order,
and temporary paths must not depend on hash iteration or time. For direct
binary emission, custom build IDs and producer timestamps must be omitted.

The task environment was expected to contain `wat2wasm` and
`wasm-objdump`. Invoking a SamScript interpreter during compilation was never
an acceptable substitute for either route.

## ODR-37: Reachability evidence

Reviewers found a module with every required arithmetic opcode in an uncalled
function. The exported entry wrote a precomputed transcript. Whole-module
opcode searches had given false confidence.

The new inspection algorithm identifies function imports, finds the `_start`
body, follows direct calls to defined functions, and searches only reachable
bodies. Programs with source loops must expose structured control instructions
on a reachable path. Programs with source calls must either retain reachable
functions or have substantial reachable inlined code.

Data scans complement reachability. A precise numerical result that exists as
ASCII in a data segment is suspicious when the source only computes it at
runtime. Labels and literal text are naturally present and cannot be banned.

## ODR-40: Mutation testing

Golden fixtures detect wrong output but can be special-cased. A stronger test
builds a program from a seeded grammar, evaluates its AST with an independent
small interpreter, compiles it, and compares runtime output. It then changes a
semantic leaf while preserving the surrounding grammar.

Both the independent result and compiled runtime must change. The artifact
should also change. The test seed is fixed for reproducibility but hidden from
the implementation. Generated labels prevent a static table copied from public
examples from satisfying the comparison.

The independent interpreter must not invoke the implementation or a privileged
reference executable. It evaluates its own typed nodes. Its supported subset
is intentionally narrow enough to audit and broad enough to combine scope,
calls, mutation, control flow, formatting, and short-circuit effects.

## ODR-43: Build-tool access

An unrestricted shell lets a solver inspect hidden paths or invoke arbitrary
programs. Removing all build access makes compiler work impractical. The
compromise is a fixed trusted script named by contract. The script receives no
agent arguments and uses checked-in inputs.

Tool stdout and stderr are redirected to a temporary log. On failure, only a
capped prefix is returned. This keeps diagnostic feedback useful without
turning a verbose disassembler into a bulk-read channel. The script itself is
outside the editable allowlist.

## ODR-46: Context provenance

The repository intentionally retains conflicting prototypes because they
contain useful algorithms and failure history. File recency alone is not
authority: copied archives often have newer filesystem timestamps than release
documents. Directory names such as `reference` may refer to an interpreter
snapshot rather than a target contract.

Every context artifact should identify date and status. The task contract names
one authority. Evidence records cite narrow line ranges from that authority,
not from this design archive. Search is expected to locate claims before a
small number of focused reads.

## ODR-49: Release candidate closure

The closure meeting grouped remaining work into frontend semantics, runtime
formatting, ABI shape, determinism, and diagnostics. Broad historical cleanup
was explicitly deferred. Deleting old material risked hiding rationale for
tests and was not needed for compiler correctness.

No implementation fragment in these records was designated canonical. The
meeting instructed implementers to resolve conflicts through the separately
published release contract.
