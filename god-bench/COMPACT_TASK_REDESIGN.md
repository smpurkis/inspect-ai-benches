# Compact GOD-Bench Task Redesign

## Goal

GOD-Bench tasks should remain difficult because of semantic reasoning, numerical
stability, invariants, and hidden edge cases, not because an agent must generate
an entire runtime, compiler, numerical library, or WASI application.

The default design target is:

- one dominant reasoning problem;
- one or two editable files;
- a natural solution of roughly 20-150 changed lines;
- supplied CLI, serialization, FFI, build, and runtime boilerplate;
- generated and metamorphic hidden tests;
- binary correctness, with patch size and output tokens retained as diagnostics.

## Redesign The Current Tasks

| Current task | Proposed compact task | Target patch |
| --- | --- | ---: |
| `cifar10-burn` | Supply the model, loader, deterministic trainer, optimizer, and serialization. Make deterministic augmentation, learning-rate scheduling, class balancing, and checkpoint selection editable. | 70-130 LOC |
| `cython-linalg` | Replace the ten-algorithm library with one real-Schur block-reordering kernel. Test 1x1/2x2 blocks, conjugate pairs, near-coincident eigenvalues, reconstruction, and orthogonality. | 90-150 LOC |
| `pandas-to-polars-single` | Supply downstream analytics. Require only lazy v2 normalization and prioritized quarantine splitting, including timestamps, DST, merchant joins, null handling, and exact schemas. | 80-140 LOC |
| `physics-2d` | Supply the complete engine. Leave circle-versus-rotated-box manifold generation and accumulated normal/friction impulse clamping incomplete. | 90-145 LOC |
| `physics-fix` | Supply the ODE systems and RK45 integrator. Require dense-output event localization for pressure-zero, horizon, and collapse events. | 60-120 LOC |
| `rust-python-pyo3` | Supply PyO3 marshaling, matrix storage, Hessenberg reduction, and wrappers. Require a Francis double-shift QR sweep and robust deflation criterion. | 110-150 LOC |
| `samscript-bootstrap` | Supply the self-hosted lexer, parser, values, imports, and CLI. Require lexical scope resolution and propagation of `return`, `break`, and `continue`. | 100-150 LOC |
| `samscript-wasi` | Supply parsing, typing, Wasm encoding, WASI runtime, and formatting. Require structured lowering of short-circuit expressions, nested loops, and early returns. | 100-150 LOC |
| `wasm-compression-wat` | Supply WASI I/O, memory management, dictionary construction, decoder, and header logic. Require canonical QuiltPress payload selection and block coalescing. | 90-150 WAT LOC |
| `wasm-lz77` | Supply WASI, the validated decoder, token emitters, and encoder loop. Require bounded longest-match search with exact tie-breaking and 32 KiB window semantics. | 70-125 WAT LOC |

### WAT Scaffolding

Do not make agents reproduce `_start`, WASI imports, argument parsing, memory
management, and file I/O. Build the submitted kernel between trusted WAT
fragments:

```text
trusted_prefix.wat
candidate_kernel.wat
trusted_suffix.wat
```

The runner concatenates these into a temporary module and runs `wat2wasm`.
Only `candidate_kernel.wat` is editable and published as a candidate artifact.

## Ten New Compact Tasks

### 1. Incremental MessagePack Decoder

- **Language:** Rust
- **Editable file:** `src/decode.rs`
- **Task:** Repair decoder state when integers and nested container headers are
  split across arbitrary input chunks.
- **Hidden verification:** Every split position, malformed prefixes,
  non-canonical integers, nesting limits, and whole-buffer versus chunked
  equivalence.
- **Target:** 70-120 LOC.

### 2. Raft Snapshot Reconciliation

- **Language:** Go
- **Editable file:** `raft/reconcile.go`
- **Task:** Repair log reconciliation across snapshot boundaries, conflicting
  terms, duplicate retries, and compacted indexes.
- **Hidden verification:** Generated leader/follower histories, idempotence,
  committed-prefix preservation, stale-leader rejection, and convergence.
- **Target:** 50-100 LOC.

### 3. Constant-Time PKCS#7 Unpadding

- **Language:** C
- **Editable file:** `src/unpad.c`
- **Task:** Correctly reject malformed padding without leaking the invalid-byte
  position or changing output on failure.
- **Hidden verification:** Every padding length and invalid position, full-block
  padding, arithmetic boundaries, and equal-length branch/load trace checks.
- **Target:** 20-45 LOC.

### 4. Transactional JSON Patch

- **Language:** TypeScript
- **Editable file:** `src/applyOperation.ts`
- **Task:** Fix RFC 6902 `move` and `copy` for shared ancestors, array index
  shifts, rollback, and deep-copy aliasing.
- **Hidden verification:** Property-generated JSON trees, escaped pointers,
  self-descendant moves, rollback, and comparison with an independent oracle.
- **Target:** 60-110 LOC.

### 5. Bitemporal Entitlement Query

- **Language:** PostgreSQL
- **Editable file:** `query.sql`
- **Task:** Resolve the entitlement effective at business time `t` as known at
  audit time `a`, including corrections and tombstones.
- **Hidden verification:** Generated overlapping valid/system intervals,
  retroactive corrections, boundary timestamps, ties, and tenant isolation.
- **Target:** 25-60 LOC.

### 6. Aligned Reallocator

- **Language:** Zig
- **Editable file:** `src/aligned_pool.zig`
- **Task:** Repair resize logic that violates alignment or loses data when an
  allocation moves.
- **Hidden verification:** Generated allocate/resize/free sequences, alignments
  through 4096, prefix preservation, overflow, coalescing, and stale pointers.
- **Target:** 70-130 LOC.

### 7. Indentation Layout Inserter

- **Language:** Haskell
- **Editable file:** `src/Layout.hs`
- **Task:** Repair virtual brace and semicolon insertion for a small
  indentation-sensitive language.
- **Hidden verification:** Equivalent indentation variants, nested `let` and
  `where`, explicit braces, comments, blank lines, and malformed dedents.
- **Target:** 50-100 LOC.

### 8. Async Cache Generation Race

- **Language:** Java
- **Editable file:** `src/main/java/VersionedCache.java`
- **Task:** Prevent an old in-flight load from publishing after invalidation
  while sharing one load among callers in the same generation.
- **Hidden verification:** Deterministically explored interleavings,
  linearizability, failure eviction, cancellation, and stale completion.
- **Target:** 60-120 LOC.

### 9. Robust Geometric Predicate

- **Language:** Python
- **Editable file:** `predicates.py`
- **Task:** Complete an adaptive `orient2d` fallback and exact segment
  classifier using supplied expansion-arithmetic primitives.
- **Hidden verification:** Nearly collinear large coordinates, exact rational
  oracle comparisons, and translation, scaling, and permutation metamorphisms.
- **Target:** 60-120 LOC.

### 10. Capability-Safe Module Loader

- **Language:** Lua
- **Editable file:** `loader.lua`
- **Task:** Prevent capability leakage, make circular imports deterministic,
  and ensure failed loads do not poison the module cache.
- **Hidden verification:** Generated import graphs and attempts to escape via
  `_G`, metatables, debug facilities, the filesystem, and package caches.
- **Target:** 70-130 LOC.

## Authoring And Verification Rules

### Scaffold incidental complexity

Supply CLI parsing, serialization, FFI marshaling, build configuration, WASI
boilerplate, allocators when allocation is not the task, parsers when lowering
is the task, and matrix primitives when convergence is the task. Do not expose a
helper that directly encodes the core invariant.

### Protect the scaffold

Only kernel files should be editable. The verifier should reconstruct pristine
files, overlay declared artifacts, reject extra source files and symlinks, and
exclude generated binaries, models, and build products.

### Use generated and metamorphic hidden tests

Each task should combine private generated cases, metamorphic transformations,
single-input mutation checks, structural reachability checks, and adversarial
boundaries. Public tests should demonstrate the interface with one normal case,
one edge case, one invariant, and a deterministic rerun without exposing the
hidden state space.

### Validate test adequacy with mutations

During benchmark authoring, replace the candidate kernel with a no-op, reverse
critical comparisons, remove bounds checks, change signs, return cached values,
and bypass the candidate call site. The hidden suite should reject each relevant
mutation.

### Preserve correctness-first scoring

Keep binary correctness as the primary leaderboard value. Retain partial public
and hidden pass fractions only as diagnostics. Report model output tokens,
changed lines, final artifact bytes, edit count, and tool usage, but do not fail
a correct solution merely for exceeding an expected line count.

### Recalibrate budgets

After compacting the tasks, begin calibration around 32k-72k model tokens for
most tasks and up to 96k for focused context-heavy tasks. Set final ceilings from
successful-run percentiles rather than retaining the temporary 200k ceiling.
