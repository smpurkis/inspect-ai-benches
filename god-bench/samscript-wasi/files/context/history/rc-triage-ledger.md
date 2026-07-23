# Release-Candidate Triage Ledger

Archive date: 2026-03-05

Status: closed issue ledger, non-normative. Resolution labels record team
intent at the time; the published release contract is the final authority.

## Frontend queue

**RC-104, power nesting:** The Pratt parser used equal binding power on both
sides of power, producing left nesting. The parser snapshot was changed to
recurse with lower right binding power. Tests use three powers because two do
not distinguish associativity. Resolution: parser patch merged.

**RC-108, unary interaction:** Prototype documentation placed power above unary
minus, while an interpreter snapshot did the reverse. Existing examples used
parentheses and did not expose the disagreement. Resolution: defer to release
precedence table; archive examples are informative.

**RC-113, newline after return:** A parser consumed the next line's expression
as the value of a bare return. Token spans showed that newline had already been
discarded by a generic whitespace helper. Resolution: statement parser now
observes newline and close brace before parsing an optional value.

**RC-117, nested interpolation:** A closing brace inside a nested call was
mistaken for the end of interpolation. Resolution: lexer balances braces and
tracks strings within expression chunks. Added cases combine calls, arithmetic,
and escaped quotes.

**RC-121, escaped dollar:** Three historical spellings appeared in tests:
double dollar, backslash dollar, and a raw dollar before a non-brace character.
Resolution: release syntax selected by authority; old template proposal tests
moved to archive.

**RC-126, comments in strings:** The desktop preprocessor stripped `//` before
string scanning. Resolution: comments are recognized by the lexer only in
ordinary source state. URL-shaped string fixtures restored.

## Binding queue

**RC-133, shadow storage:** Binding allocation keyed WebAssembly locals by name.
An inner declaration then reused the outer slot. Resolution: declarations gain
stable identities; name maps point to identities and storage maps identities to
locals.

**RC-137, branch leakage:** A declaration inside a true branch remained in the
frontend map after the branch ended. Resolution: scope guards restore map depth
on every normal and exceptional lowering exit.

**RC-141, loop mutation:** A proposed interpretation forbade assignment through
an outer scope, making ordinary loop counters unusable. Interpreter behavior
and newer design notes disagreed with an archived sentence. Resolution: release
rules and conformance programs determine behavior; stale prose not promoted.

**RC-145, immutable compound assignment:** Direct assignment checked immutable
bindings but the compound path wrote the local after arithmetic without the
check. Resolution: both paths call one resolved-binding assignment helper.

**RC-149, default order:** Defaults were evaluated in the caller before any
parameters were bound. A default referring to an earlier parameter failed.
Resolution: arguments evaluate left to right, call frame is created, explicit
parameters bind, then missing defaults evaluate in order.

## Control queue

**RC-156, continue depth:** Nested `if` blocks inside a loop emitted a branch
depth computed before an extra block was inserted. WAMR caught the invalid
depth while one optimizer rewrote it successfully. Resolution: represent break
and continue targets symbolically until structured emission.

**RC-160, return from loop:** Return was lowered as a branch to the loop exit,
then execution continued after the loop. Resolution: function return uses a
dedicated epilogue target and result local, independent of loop targets.

**RC-164, eager logical right side:** Normalizing both operands before selecting
`i32.and` preserved values but not effects. Resolution: branch around right-side
lowering and write a normalized boolean result local.

**RC-169, recursive signatures:** Function result type was inferred while its
body lowered. A recursive call saw the placeholder unit result. Resolution:
declaration pass records signatures before any body pass.

**RC-172, forward declaration order:** Function indices came from hash-map
iteration, producing nondeterministic artifacts. Resolution: assign indices by
source declaration order and use ordered maps for auxiliary emission.

## Runtime queue

**RC-181, positive and negative zero divisors:** The check compared raw bits to
positive zero and missed negative zero. Resolution: numeric equality check
before division or remainder catches both signed zeros.

**RC-185, dynamic zero folding:** A data-flow pass proved a local zero and
reported a compile error intended only for literal zero. This changed when
minor source edits defeated propagation. Resolution: only syntactic literal
zero receives optional compile diagnosis; dynamic paths retain runtime checks.

**RC-190, write count address:** The byte-count result overlapped the second
iovec in two-record print calls. Resolution: reserve separate aligned runtime
slots and document the memory map in emitter tests.

**RC-194, short writes:** Writer assumed one syscall wrote all bytes. Resolution:
runtime loops over remaining records. A zero-byte successful write is treated
as failure to avoid an infinite loop.

**RC-199, allocator page units:** High-water bytes were compared with page
count. Resolution: round byte requirement to 64 KiB pages before comparison;
check arithmetic overflow before `memory.grow`.

**RC-203, UTF-8 length:** Builtin returned byte length. Resolution: scalar-count
loop counts bytes that are not continuation bytes, relying on valid source and
runtime-produced UTF-8.

**RC-208, decimal suffix:** All numbers received six decimal digits. Resolution:
finite exact integral values take an integer formatting path; other finite
values use the selected shortest formatter.

## Artifact queue

**RC-217, successful-looking failure output:** Assembler failure left a previous
output file in place. Resolution: compile to a temporary sibling, validate, and
atomically replace destination only after success; remove temporary files on
failure.

**RC-221, embedded paths:** A producer custom section included the temporary WAT
path. Resolution: omit nonessential producer metadata. Determinism checks now
compile in distinct temporary directories.

**RC-225, dead proof functions:** Opcode compliance helper was present but
uncalled. Resolution: structural tests walk calls from `_start`; dead bodies do
not contribute evidence.

**RC-229, output transcript folding:** Whole-program evaluator replaced source
computation with a data segment. Resolution: pass removed. Local pure folding
remains possible, but loops, calls, mutation, formatting, and writes execute in
the generated module.

**RC-234, import namespace:** A copied helper emitted `wasi_unstable` while its
comments claimed preview1. Resolution: ABI tests inspect import module and
function signatures, not comments or helper names.

**RC-238, entry aliases:** Backend exported `main`, `_initialize`, and `_start`.
Resolution: command artifact exports only the contract-required entry and
memory unless another export is explicitly needed.

## Verification queue

**RC-247, fixture specialization:** Public and hidden fixed examples shared
recognizable labels. Resolution: retain fixtures for diagnostics but add seeded
AST generation with opaque labels and paired semantic mutation.

**RC-251, circular oracle:** Compiler output was compared with an interpreter
invoked by the compiler itself. Resolution: hidden oracle evaluates independent
Python nodes and the compiler process has no expected-output input.

**RC-255, permissive errors:** A test accepted zero exit when the word `error`
appeared on stdout. Resolution: dynamic runtime faults assert exact process
status; class-specific checks are made where diagnostics are part of the
profile.

**RC-260, uncapped disassembly:** Build feedback returned an entire object dump,
creating an unintended bulk channel. Resolution: fixed trusted smoke redirects
tool output and returns one bounded prefix only on failure.

**RC-264, mutable smoke script:** An early allowlist included every Python and
shell file. Resolution: only task deliverables are editable; trusted scripts
and probe inputs are immutable visible context.

**RC-268, evidence by filename:** Submission cited a file named `reference`
without checking contract authority. Resolution: evidence schema names one
authority and validates narrow in-range citations that contain required claims.

## Closure

The triage chair closed the ledger after mapping every accepted item to either
a conformance test, a compiler work item, or release text. Historical status
codes, numeric models, import modules, and interpolation spellings were left in
place in archived files to preserve provenance. Implementers were instructed
to search by semantic claim, inspect nearby context, and cite only the authority
selected by the machine-readable task contract.
