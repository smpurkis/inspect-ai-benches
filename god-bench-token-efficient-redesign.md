# GOD-Bench: Token- and Tool-Efficient Redesign Specification

**Status:** proposed implementation plan
**Scope:** active tasks in `god-bench/`, common Inspect harness, score reporting, and a small intentional long-context track
**Primary goal:** retain or increase task difficulty while sharply reducing unnecessary model tokens, tool calls, wall-clock exploration, and test-feedback leakage.

---

## 1. Executive decision

Adopt a **correctness-first, efficiency-rewarded** benchmark.

A submission must pass the hidden test suite to receive meaningful credit. Among correct submissions, use fewer billed tokens, fewer weighted tool calls, fewer repeated/no-progress actions, and less elapsed time to earn a higher score.

Do **not** rank models by raw token count or raw tool-call count across all attempts. A model that immediately guesses, gives up, or fails cheaply must not outrank a model that solves the task.

Use two task families:

1. **Core-GOD** — 8–10 compact, high-difficulty software/numerical/compiler tasks. Each task has a 50–180 token task card, narrow edit scope, deterministic public smoke tests, generated hidden tests, and hard exploration limits.
2. **GOD-Context** — 3–5 intentionally long-context tasks. Each task still has a short task card, but the workspace contains 16k–128k tokens of realistic code, traces, specifications, commits, and distractors. These measure selective retrieval and evidence grounding, not ability to consume repeated filler.

The benchmark therefore distinguishes:

- capability to solve difficult engineering work;
- ability to do so economically;
- ability to identify relevant evidence inside a large workspace.

---

## 2. Problems in the current harness

The common harness at `god-bench/common/staged_eval.py` has the following behavior:

- It injects visible files and tells the agent: `Read /app/files/instructions.md for full task details.`
- It supplies `bash` and `python` tools through `use_tools(...)`.
- It calls `generate(state, tool_calls="loop")`, which permits iterative tool use until the model decides to stop.
- It allows each bash invocation up to 900 seconds, hidden-test execution up to 1,200 seconds, and public test output uses verbose pytest (`-vv -rA`).
- The existing scorer records only a reward based on passed-test fraction. It does not track cost, tool calls, no-progress loops, or token use.

This is an excellent baseline for functional evaluation but not for token efficiency. The design permits an agent to read too many files, rerun commands, request large test logs, and continue for hundreds of turns. The changes below make these behaviors measurable and bounded.

---

## 3. Non-negotiable evaluation principles

### 3.1 Correctness gates efficiency

For each task attempt:

- Hidden tests fail: functional score is `0`.
- Hidden tests pass: the task is solved; efficiency determines additional credit and ranking.

Never apply a formula where a cheap failed run can receive a higher score than an expensive correct run.

### 3.2 Minimize language, not intellectual work

Replace prose explanations and large hand-authored fixture descriptions with:

- exact function signatures;
- short adjacent docstrings;
- compact machine-readable contracts;
- public smoke tests;
- hidden property tests and reference-oracle checks.

The model should need to reason about code, algorithms, numerical behavior, and edge cases—not read a tutorial.

### 3.3 Restrict observations, not legitimate solving

A hard task can require several hypothesis/test cycles. Do not simply set a tiny universal turn cap. Instead:

- allow a sensible bounded budget;
- cap expensive/repeated actions more aggressively;
- return concise, categorized feedback;
- require an actual file change before an identical test command can be rerun;
- reserve larger budgets for explicitly designated GOD-Context tasks.

### 3.4 Hidden tests should be stronger than visible tests

Public tests teach the API and enable basic validation. Hidden tests establish actual difficulty through randomized seeds, reference implementations, metamorphic properties, security checks, and anti-hardcoding checks.

---

## 4. Standard task contract

Every Core-GOD task should have this visible structure:

```text
<task>/
  compose.yaml
  eval.yaml
  run.py
  files/
    TASK.md                 # ≤180 tokens; task card
    contract.toml           # authoritative machine-readable contract
    README.md -> TASK.md    # optional compatibility alias
    src/...                 # read-only except explicitly writable targets
    tests_public.py         # public smoke tests only
    schema.json             # when input/output needs a schema
  hidden/
    hidden_tests.py
    generators.py
    reference_impl.py       # hidden oracle where appropriate
    anti_cheat.py
```

### 4.1 `TASK.md`

Target: 50–180 words. It must state only:

- exact editable files;
- exact entry point / CLI;
- one line of behavioral objective;
- one line of constraints;
- one public test command;
- no conceptual tutorial, repeated examples, or test-case catalogue.

Example:

```md
Implement TODOs in `pipeline_polars.py`; do not change its public API.

The output must match `reference.py` for valid inputs. Ordering and schema
are contractual; pandas and network access are forbidden. Run `pytest -q
/app/files/tests_public.py`. Hidden tests include schema evolution, nulls,
time zones, joins, and ordering.
```

### 4.2 `contract.toml`

Use this to make constraints queryable without prose:

```toml
[task]
id = "polars-semantic-diff"
entry = "/app/files/pipeline_polars.py"
public_test = "pytest -q /app/files/tests_public.py"

[limits]
max_agent_turns = 24
max_weighted_tool_cost = 44
max_public_test_runs = 3
max_file_read_bytes = 180000
wall_clock_seconds = 900

[policy]
network = false
editable = ["pipeline_polars.py"]
forbid_imports = ["pandas"]
require_determinism = true
```

The agent does not need to consume the whole file if the task card exposes the material constraints. The harness uses it to enforce limits.

### 4.3 Restrict edit scope

Make all visible files read-only except the exact intended implementation file(s). The current harness already has `writable_patterns`; supply it in every task `run.py` and keep it narrow.

Good:

```python
return create_task(
    challenge_dir=Path(__file__).resolve().parent,
    writable_patterns=["pipeline_polars.py"],
)
```

Avoid granting blanket write access to `**/*`. If a task legitimately needs generated output, permit only a named directory such as `out/**`.

---

## 5. Task conversion plan

### 5.1 `physics-fix` → `gr-ode-repair`

**Keep:** TOV integration, collapse event detection, numerical stability, physical invariants, Rust implementation.

**Remove from prompt:** astrophysics tutorial, long execution walkthrough, large concrete examples.

**Visible materials:**

- `src/solver.rs` with TODOs and compact equation comments;
- `contract.toml` with allowed error tolerances;
- 3–5 smoke cases.

**Hidden tests:**

- randomized EOS parameters;
- mass monotonicity and non-negative pressure;
- surface matching to a Schwarzschild reference;
- integration convergence when step size is halved;
- horizon crossing and event order;
- finite output and deterministic output;
- comparison against a tight-tolerance oracle.

**Task card:**

```md
Implement marked routines in `src/solver.rs`. Preserve CLI/API behavior.
Solutions must be deterministic, finite, physically admissible, and meet
residual tolerances. Run `cargo test --quiet`.
```

### 5.2 `cython-linalg` → `restricted-linalg-kernel`

**Keep:** Cython-only numerical computation and stability/performance demands.

**Visible materials:** function signatures, a short per-function docstring, build script, 4–8 smoke checks.

**Hidden tests:** seeded matrices spanning condition numbers; QR/SVD reconstruction; orthogonality; residual bounds; singular and nearly singular inputs; shape errors; AST/import checks against NumPy/LAPACK/BLAS delegation; selected performance thresholds.

**Task card:**

```md
Complete marked functions in `cylinalg.pyx`. Numerical libraries are forbidden
inside the extension. Match the documented API and numerical tolerances.
Build and test with `python setup_build.py build_ext --inplace && pytest -q`.
```

### 5.3 `rust-python-pyo3` → `ffi-linalg-kernel`

Use the same behavioral corpus as Cython plus PyO3-specific failure modes:

- shape/dtype errors;
- contiguous/noncontiguous arrays;
- error conversion to the expected Python exception;
- no unintended memory aliasing;
- Rust-only storage/computation;
- dependency lock verification.

### 5.4 `pandas-to-polars-single` → `polars-semantic-diff`

This is the largest prompt-compression opportunity.

**Replace:** long migration narrative and multiple prose-heavy reference pipelines.

**With:**

- `reference.py` as read-only executable oracle;
- `pipeline_polars.py` containing TODOs;
- `contract.toml` with output schema, sort policy, null policy, and timezone policy;
- a small public input corpus.

**Hidden generated cases:** renamed/missing columns, schema versions, duplicate events, nulls, daylight-saving transitions, categorical values, join-cardinality variations, window boundaries, ordering, lazy/eager equivalence.

The difficult part remains exact semantic matching, but the model no longer needs to ingest a multi-thousand-word business-rule explanation.

### 5.5 `physics-2d` → `contact-solver`

**Visible:** CLI signature, JSON Schema, `physics2d.py` with stubs, five smoke tests.

**Hidden:** OBB rotation cases, circle/OBB grazing contacts, high-speed impacts, stacked bodies, friction, translation/rotation invariance, permutation invariance, non-increasing penetration, stable time-step refinement, deterministic result hashes.

Do not show a long JSON tutorial. A JSON Schema and one minimal example are enough.

### 5.6 `samscript-bootstrap` → `self-hosted-interpreter-core`

Keep a compact EBNF grammar and builtin table, ideally 400–800 tokens total. Generate hidden source programs from the grammar and compare output to the reference implementation.

Hidden coverage: precedence, recursion, scope, mutation, interpolation, escaped strings, runtime errors, randomized ASTs, anti-cheat checks for use of the reference binary or canned output.

### 5.7 `samscript-wasi` → `sam2wasi`

Use as one of the long-context tasks. Keep a short authoritative semantic specification, but provide a deliberately large realistic workspace with a reference interpreter, old compiler fragments, ABI notes, example programs, version history, and distractor documents.

Require a small `evidence.json` on completion:

```json
{"authority":"spec/semantics.md","evidence":["spec/semantics.md:41-62"]}
```

This costs very few output tokens while measuring whether the model identified the authoritative material.

### 5.8 `wasm-compression-wat` and `wasm-lz77`

These are naturally compact. Replace long prose algorithm descriptions with a concise binary-format table and function contract.

Hidden tests should cover random bytes, repeated blocks, incompressible streams, overlapping backreferences, 32 KiB window boundaries, malformed data, deterministic encoding, resource ceilings, and anti-delegation checks.

### 5.9 `cifar10-burn` → `deterministic-vision-pipeline`

This is primarily compute-expensive, not language-expensive. Make it low-language by:

- giving only fixed paths, entry points, output artifact names, reproducibility requirements, and test command;
- suppressing epoch logs and large metric dumps;
- using a curated small dataset plus perturbation-based held-out checks;
- checking deterministic prediction/model hashes across two runs;
- enforcing a compute/time cap and no pretrained artifacts.

---

## 6. Deliberate long-context track

Long context must contain useful, heterogeneous evidence rather than repeated filler. Use only 3–5 such tasks so they do not dominate benchmark cost.

### 6.1 Repository provenance repair

- Workspace: 40k–100k tokens of source, commits, changelog excerpts, old implementations, and irrelevant modules.
- Objective: one targeted defect fix.
- Difficulty: identify source of truth and causal path.
- Tests: hidden regression and mutation tests.

### 6.2 Conflicting-spec compiler

- Workspace: 20k–60k tokens of docs, old examples, language spec, and compiler code.
- Only one document is authoritative; older docs conflict in subtle ways.
- Objective: implement/fix one feature.
- Tests: grammar-generated programs targeting conflict points.

### 6.3 Incident-to-patch

- Workspace: 30k–80k tokens of traces, metrics snapshots, configuration, code, and incident notes.
- Objective: patch root cause and emit a three-field root-cause JSON.
- Tests: replay traces plus fault-injection variants.

### 6.4 API migration with scattered contracts

- Workspace: 40k–100k tokens spread among code, deprecation notices, fixtures, and client contracts.
- Objective: a constrained compatibility-preserving migration.

### 6.5 Scientific audit

- Workspace: numerical implementation, paper excerpt, derivation notes, experiment records.
- Objective: repair sign/boundary/normalization/stability bug.
- Tests: convergence, conservation, and perturbation robustness.

### 6.6 Long-context controls

Even long-context tasks need efficient behavior:

- Prompt remains ≤140 tokens.
- Workspace is file-based, never pasted wholesale into the initial prompt.
- Full-file reads are capped; the tool should require line ranges or return the first 200 lines by default.
- Relevant evidence is sparse (about 2–5% of workspace), distributed across 2–5 sources.
- Tool-return size is capped; `grep` results show a small number of matching lines with paths and ranges.
- Log retrieval precision: relevant files opened / all files opened.
- Long-context tasks receive a larger but still finite exploration budget.

---

## 7. Exploration governance: preventing 200+ turns

### 7.1 Define three separate budgets

Do not only cap turns. Track all of these:

| Budget | Core-GOD default | GOD-Context default | Reason |
|---|---:|---:|---|
| Agent turns | 24 | 48 | Limits unbounded reasoning/tool loops |
| Weighted tool cost | 44 | 80 | Prices expensive operations correctly |
| Public test runs | 3 | 5 | Prevents trial-and-error exploitation |
| File-read bytes | 180 KB | 1.5 MB | Prevents workspace dumping |
| Wall clock | 15 min | 30 min | Prevents slow loops / hung processes |
| Same command without edit | 0 | 0 | Stops pointless retries |

Tune budgets using baseline runs. They should be large enough for a strong agent to solve, but small enough that a 200-turn exploratory run terminates well before 200 turns.

### 7.2 Weighted tool-cost schedule

Raw count is not sufficient. Assign costs:

| Action | Cost | Escalation |
|---|---:|---|
| Search/list (`rg`, `find`, `ls`) | 1 | +1 after 8 searches |
| Read a source range | 1 | +1 after 12 reads |
| Write/edit | 1 | none |
| Build/lint | 2 | +1 after 5 |
| Public test run | 5 | +3 after the second run |
| Full test suite / expensive training | 8 | +5 after first run |
| Repeated command with no file edit | 8 | deny after one repeat |
| Oversize read / `cat` huge file | 6 | truncate response |

A model should not be penalized for editing. It should be penalized for repeatedly observing or testing without learning.

### 7.3 Define “progress” mechanically

Maintain a state fingerprint after every tool action:

- SHA-256 of all editable files;
- normalized command signature;
- last public-test summary;
- current remaining budgets.

A test/build command is **no-progress** if the editable-file fingerprint is unchanged since its previous invocation and the normalized command is identical. Deny it with a short response:

```text
Denied: identical test command after no editable-file change. Edit code or inspect a new hypothesis.
```

A read/search is **low-value repeated exploration** if it repeats the same file range or same normalized query. Return a cache hit, not the original content:

```text
Cached: identical read already returned at tool call 7. 0 budget charged.
```

After repeated low-value calls, return:

```text
Exploration budget exhausted. You may edit, inspect previously unseen files, or run the final public test once.
```

### 7.4 Force a plan before tools

Require a short structured plan at the beginning, capped at 120 tokens:

```json
{
  "target_files":["pipeline_polars.py"],
  "hypothesis":"TODOs must match reference output semantics",
  "first_check":"read TODOs and public tests"
}
```

Do not grade the plan for eloquence. Use it to record intended scope. If the agent later reads 40 unrelated files, the trace clearly shows exploration drift.

### 7.5 Add checkpoint prompts, not endless feedback

At 50% and 80% of budget, inject one short message:

```text
Budget checkpoint: 12/24 turns and 26/44 tool cost used. Prioritize an implementation and one validating test run.
```

At the final reserve, disable broad searches and large reads but still allow edits and one final test:

```text
Finalization mode: broad exploration is disabled. You may edit writable files and run one public test command.
```

This is superior to abruptly terminating a promising agent with no opportunity to synthesize.

### 7.6 Cap tool output

Current verbose pytest mode (`-vv -rA`) can return excessive text. Change public test command construction to quiet output and machine-readable summary:

```bash
python -m pytest -q --tb=short --disable-warnings /app/files/tests_public.py
```

Then normalize return feedback to:

```text
public tests: 7/9 passed
failure category: timezone_ordering
assertion: expected sorted UTC timestamps; first mismatch at row 3
```

Do not return full arrays, random generator inputs, long stack traces, hidden expected values, or more than one representative failure per category.

### 7.7 Make tool interfaces purpose-built

Do not give unrestricted shell access if token efficiency is central. Expose controlled tools or wrap bash commands:

- `search(query, path, max_results=20)`
- `read(path, start_line, end_line, max_chars=8000)`
- `edit(path, patch)`
- `run_public_tests(target="default")`
- `build(target="default")`

This enables reliable accounting and output truncation. If unrestricted bash must remain, wrap the executor to parse and gate known patterns, apply output limits, and reject network/process escapes.

---

## 8. Scoring: correctness first, efficiency rewarded

### 8.1 Publish three leaderboards

1. **Capability leaderboard:** hidden-test pass rate.
2. **Budgeted capability leaderboard:** pass rate within task budgets.
3. **Efficiency leaderboard:** efficiency-adjusted score among correct attempts.

Never replace raw capability with a single cost-weighted number. Researchers need to see whether a model is incapable, capable but costly, or capable and efficient.

### 8.2 Per-task score

Let:

- `P` = 1 if all hidden tests pass; else 0;
- `T_u` = total billed tokens used by agent messages plus tool-return text;
- `T_b` = per-task token budget;
- `C_u` = weighted tool cost used;
- `C_b` = tool-cost budget;
- `R_u` = count of no-progress retries;
- `R_b` = retry allowance, normally 0 or 1.

Use:

\[
S = P \times E_T \times E_C \times E_R
\]

where:

\[
E_T = \min\left(1, \sqrt{\frac{T_b}{\max(T_u,1)}}\right)
\]

\[
E_C = \min\left(1, \sqrt{\frac{C_b}{\max(C_u,1)}}\right)
\]

\[
E_R = \frac{1}{1 + 0.05\max(0,R_u-R_b)}
\]

The square-root terms deliberately impose a mild penalty. A correct model should not be heavily punished for using 1.2–1.5x a guideline budget, while a model using 5–10x the budget should score noticeably lower.

### 8.3 Budget-tier alternative

If a continuous formula is undesirable, use tiers:

| Outcome | Task score |
|---|---:|
| Hidden pass; under token and tool budget | 1.00 |
| Hidden pass; ≤1.5x either budget | 0.90 |
| Hidden pass; ≤2x either budget | 0.75 |
| Hidden pass; over 2x budget | 0.50 |
| Hidden fail | 0.00 |

For leaderboard ordering:

1. Hidden pass count.
2. Under-budget pass count.
3. Sum of efficiency scores.
4. Median total tokens on solved tasks.
5. Median weighted tool cost on solved tasks.
6. Median elapsed time.

### 8.4 Do not reward zero usage

Set a **minimum observation floor** only for diagnostic reporting, not scoring. Some tasks genuinely require reading source and tests. Do not award an additional bonus for suspiciously tiny use; hidden tests already prevent blind guessing from scoring.

### 8.5 Score partial correctness separately

Keep the present partial test fraction only as diagnostic metadata:

- `public_pass_fraction`
- `hidden_pass_fraction`
- `failure_category`

Do not mix partial credit into the efficiency leaderboard. Otherwise a cheap 20% solution may distort comparison with a correct but expensive solution.

---

## 9. Harness implementation plan

### 9.1 Add a budget object

Create `god-bench/common/budgeted_eval.py` or extend `staged_eval.py`.

```python
from dataclasses import dataclass, field
from time import monotonic

@dataclass
class Budget:
    max_turns: int
    max_weighted_tool_cost: int
    max_public_tests: int
    max_file_read_bytes: int
    max_wall_clock_seconds: int
    turns: int = 0
    weighted_tool_cost: int = 0
    public_tests: int = 0
    file_read_bytes: int = 0
    no_progress_retries: int = 0
    started_at: float = field(default_factory=monotonic)

    def exhausted(self) -> bool:
        return (
            self.turns >= self.max_turns
            or self.weighted_tool_cost >= self.max_weighted_tool_cost
            or self.public_tests >= self.max_public_tests
            or self.file_read_bytes >= self.max_file_read_bytes
            or monotonic() - self.started_at >= self.max_wall_clock_seconds
        )
```

Read limits from a task-specific `contract.toml`; provide conservative defaults for old tasks.

### 9.2 Replace open-ended `tool_calls="loop"`

The present call:

```python
state = await generate(state, tool_calls="loop")
```

is the main source of unbounded exploration. Replace it with an explicit bounded loop that invokes one model/tool step at a time, checks the budget after every step, and changes tool availability as the run nears exhaustion.

Pseudocode:

```python
for turn in range(budget.max_turns):
    state.metadata["budget"] = budget.as_dict()
    state = await generate(state, tool_calls="single")

    usage = collect_usage_since_last_step(state)
    budget.apply(usage)

    if budget.in_finalization_mode:
        state.messages.append(ChatMessageUser(
            content="Finalization mode: edit and run one final public test; broad exploration is disabled."
        ))
        tools = finalization_tools

    if model_completed(state) or budget.exhausted():
        break
```

Use the exact Inspect API version available in the environment; the essential requirement is that tool calls are mediated after every action rather than delegated to an unconstrained loop.

### 9.3 Instrument every tool

For every tool event, record:

```json
{
  "turn": 11,
  "tool": "bash",
  "normalized_command": "pytest -q /app/files/tests_public.py",
  "class": "public_test",
  "tool_cost": 5,
  "input_chars": 44,
  "output_chars": 367,
  "read_bytes": 0,
  "editable_fingerprint_before": "...",
  "editable_fingerprint_after": "...",
  "no_progress": false,
  "elapsed_seconds": 2.6
}
```

Store this in `/logs/verifier/agent_usage.json`. It must be available to the scorer after the run.

### 9.4 Track tokens accurately

Record separately:

- model input/prompt tokens;
- model output/completion tokens;
- tool output tokens/characters converted using the provider’s tokenizer where possible;
- benchmark boilerplate tokens;
- user/model-provided task text.

The primary efficiency figure should be **model-billed total tokens**. Publish tool-return text as a separate diagnostic because harness verbosity can otherwise distort model comparison.

### 9.5 Update pytest command construction

Change `_stage_pytest_shell(..., verbose=True)` default to `verbose=False` for public loops. Use a separate hidden command with controlled logs. Never give hidden output to the model.

Suggested public command:

```python
verbosity = "-q --tb=short --disable-warnings"
```

After a public test run, parse and return only a compact normalized summary. Preserve the full raw logs privately in verifier artifacts for debugging benchmark authoring.

### 9.6 Update `staged_scorer`

Add metrics and metadata. The scorer should:

1. Read functional reward/status as before.
2. Read usage trace.
3. Compute `hidden_pass`, total tokens, weighted tool cost, no-progress count, elapsed time, and efficiency score.
4. Return raw correctness as the principal `Score.value` if your evaluator expects a single raw correctness metric.
5. Attach `efficiency_score` and all usage numbers as named metrics/metadata for leaderboard aggregation.

Example metadata:

```python
metadata={
    "functional_pass": True,
    "functional_reward": 1.0,
    "efficiency_score": 0.87,
    "model_input_tokens": 8321,
    "model_output_tokens": 2174,
    "tool_output_tokens": 3950,
    "total_tokens": 14445,
    "weighted_tool_cost": 31,
    "tool_calls": 14,
    "public_test_runs": 2,
    "no_progress_retries": 0,
    "elapsed_seconds": 425.8,
    "budget": {...},
}
```

### 9.7 Preserve backward compatibility

Create an opt-in mode first:

```python
create_task(
    challenge_dir=...,
    writable_patterns=[...],
    budget_mode="strict",
)
```

Keep old tasks runnable as `budget_mode="legacy"` while migrating. Once task contracts and baselines are validated, make strict mode the default.

---

## 10. Public test feedback design

Public tests must help competent agents debug without making exploration cheap or leaking the hidden oracle.

### Return

- pass count and total count;
- one failure category;
- one concise normalized assertion;
- optional file/function location;
- runtime category if timeout/performance failure.

### Do not return

- full tracebacks by default;
- all failures;
- full expected/output arrays;
- random hidden seed/data;
- the implementation of reference or hidden tests;
- unlimited stderr/stdout;
- repeated copies of identical test output.

Example:

```text
public: 5/7 passed
category: null_groupby
assertion: groups with only null values must emit null, not 0
```

---

## 11. Anti-gaming checklist

Every task should include the relevant checks below.

- Generated hidden inputs, not a fixed visible answer corpus.
- Multiple random seeds per run, retained privately for reproducibility.
- Reference-oracle comparisons where feasible.
- Metamorphic transformations: permutation, scaling, translation, schema renaming, split/merge, encoding roundtrip.
- Static source checks for forbidden libraries, subprocesses, network access, fixture lookups, and precomputed output files.
- Isolated container with no network and no hidden test access.
- Repeated deterministic run checks.
- Resource limits preventing brute-force methods.
- Test order randomization.
- Hidden mutation tests to ensure code is actually used.
- No public detailed oracle output.

---

## 12. Calibration process

Do not set budgets by intuition alone.

1. Implement strict harness tracing while leaving budgets permissive.
2. Run 3–5 capable agent/model baselines plus one intentionally weaker baseline.
3. Inspect distributions for successful runs: turns, tokens, weighted tool cost, test runs, read bytes, elapsed time.
4. Set Core-GOD budgets approximately near the 75th–85th percentile of competent successful runs, not the median.
5. Set GOD-Context budgets separately; they require more retrieval.
6. Verify that a known 200-turn wandering policy is cut off early and scores lower even if it eventually passes.
7. Re-run each task several times to ensure generator seeds do not create high variance or accidental impossibility.
8. Publish task-level budgets before evaluating external models.

Suggested initial budgets:

| Task type | Turns | Tool cost | Public tests | Read bytes |
|---|---:|---:|---:|---:|
| Core numerical / coding | 20–24 | 36–44 | 3 | 120–180 KB |
| Compiler / interpreter | 28–36 | 52–64 | 4 | 250–400 KB |
| ML / expensive build | 20–28 | 40–52 | 2 | 180 KB |
| GOD-Context 16k–32k | 36–44 | 64–72 | 4 | 750 KB |
| GOD-Context 64k–128k | 44–56 | 80–96 | 5 | 1.5 MB |

---

## 13. Acceptance criteria

A migrated task is ready only when all are true:

- [ ] Task card is ≤180 words.
- [ ] Exact edit scope is enforced.
- [ ] Public tests are compact and deterministic.
- [ ] Hidden tests include generated/adversarial cases.
- [ ] Hidden test failures never reach the model.
- [ ] Public test feedback is normalized and capped.
- [ ] The task emits a complete usage trace.
- [ ] A 200-turn unproductive policy cannot exceed the configured turn/tool budget.
- [ ] Repeated identical test runs without edits are denied.
- [ ] Correctness and efficiency metrics are both recorded.
- [ ] A cheap failure never ranks above a correct run.
- [ ] At least one competent baseline can solve under the calibrated budget.
- [ ] At least one weaker baseline fails or exceeds the budget.
- [ ] The task preserves the intended capability target relative to its predecessor.

---

## 14. Recommended rollout order

1. Implement generic budget/usage instrumentation in `common/staged_eval.py`.
2. Convert the compact WAT tasks first: `wasm-lz77`, `wasm-compression-wat`.
3. Convert `cython-linalg` and `rust-python-pyo3` using shared generative tests.
4. Convert `pandas-to-polars-single` and `physics-2d`, where prompt reductions are largest.
5. Convert `physics-fix` and `samscript-bootstrap`.
6. Turn `samscript-wasi` into the first GOD-Context benchmark.
7. Redesign `cifar10-burn` to be quiet and deterministic.
8. Add three additional GOD-Context tasks only after the strict harness has been calibrated.
9. Publish raw capability and budgeted-efficiency leaderboards side by side.

---

## 15. Final policy statement

> GOD-Bench rewards solving hard tasks correctly. It rewards economical solving only after correctness is established. It limits aimless exploration, excessive test probing, and verbose harness feedback. Long context remains available where it measures genuine selective retrieval over useful artifacts, not filler consumption.
