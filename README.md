# inspect-ai-benches

A monorepo of structured evaluation suites for LLM benchmarking using
[inspect-ai](https://github.com/nousresearch/inspect-ai). Contains several
benchmark collections that probe different axes of model capability —
hardened agentic tasks, broad multi-category evals, long-context retrieval,
and repository-level reasoning.

## Benchmarks

### god-bench

A hardened benchmark suite of ~15 tasks designed so that frontier models
score near zero. Each task requires genuine reasoning, tool-building, or
domain expertise — not pattern-matching. Tasks include:

- **physics-fix** — GR collapsing star simulation (TOV + Oppenheimer-Snyder)
- **cython-linalg** — 10-hard-op linear algebra via Cython
- **rust-python-pyo3** — mirror of cython-linalg in Rust PyO3
- **samscript-bootstrap / samscript-wasi** — WebAssembly compression
- **wasm-compression-wat / wasm-lz77** — WASM binary compression
- **pandas-to-polars-single** — complex polars porting
- **physics-2d / cifar10-burn** — physics simulation / ML inference
- **archive/** — 17 retired tasks from earlier iterations

Run a single task or all of them:

```bash
uv run python run_bench.py                              # god-bench only
uv run python run_bench.py --all                        # include archive
uv run python run_bench.py --tasks physics-fix
uv run python run_bench.py --models gpt-5 --rounds 3
uv run python run_bench.py --parallel 10
```

### sanity-bench

A lightweight, broad-coverage eval with ~690 tasks across 17 categories.
Designed for quick model sanity checks without running the full god-bench
suite. Deterministic scoring — no LLM-as-judge.

**Categories:** coding, coding_debug, common_sense, creative_writing,
general_knowledge, incident_scenarios, instruction_following, long_context,
math, multilingual, reasoning, safety, structured_output,
structured_synthesis, system_design, tool_use, writing

```bash
uv run inspect eval sanity-bench/run.py@math \
    --model openai-api/local/your-model \
    --env LOCAL_BASE_URL=http://localhost:8234/v1 \
    --env LOCAL_API_KEY=secret

uv run inspect eval sanity-bench/run.py \
    --model openai-api/local/your-model
```

Scoring is deterministic (exact_match, regex, contains, code_exec_python,
json_schema, length_range, refusal detection, composite). See
`sanity-bench/schema.md` for the full task/scoring reference.

### reporeason-bench

Evaluates a model's ability to reason about entire repositories —
understanding codebase structure, finding relevant code, and answering
questions that require cross-file context.

### roses-longctx-bench

Long-context evaluation tasks probing needle-in-a-haystack retrieval,
multi-document conflict QA, and summarization at 8k–30k token lengths.

### ruler/

A vendored copy of NVIDIA's [RULER](https://github.com/NVIDIA/RULER)
long-context evaluation framework (synthetic benchmarks for retrieval,
multi-hop tracing, aggregation, and QA). Evaluates effective context
size beyond simple needle-in-a-haystack.

## Project Structure

```
inspect-ai-benches/
├── run_bench.py              # Unified runner for god-bench
├── pyproject.toml             # Project dependencies
├── god-bench/                # Hardened benchmark suite
│   ├── run_all.py
│   ├── common/               # Shared eval harness helpers
│   ├── archive/              # Retired tasks
│   ├── physics-fix/          # GR collapsing star simulation
│   ├── cython-linalg/        # Linear algebra (Cython)
│   ├── rust-python-pyo3/     # Linear algebra (Rust PyO3)
│   ├── samscript-bootstrap/  # WebAssembly compression
│   ├── samscript-wasi/       # WASM compression
│   ├── wasm-compression-wat/ # WASM binary compression
│   ├── wasm-lz77/            # LZ77 compression
│   ├── pandas-to-polars-single/
│   ├── physics-2d/
│   ├── cifar10-burn/
│   └── hello-world/
├── sanity-bench/             # Broad-coverage multi-category eval
│   ├── run.py                # 17 @task functions
│   ├── scoring.py            # Deterministic scorers
│   ├── tasks/                # YAML task definitions per category
│   └── schema.md             # Task/scoring format reference
├── reporeason-bench/         # Repository-level reasoning eval
├── roses-longctx-bench/      # Long-context eval tasks
├── ruler/                    # NVIDIA RULER long-context framework
└── logs/                     # Evaluation result archives
```

## Quickstart

```bash
# Install dependencies
uv sync

# Run god-bench (hardened tasks)
uv run python run_bench.py

# Run sanity-bench (broad coverage)
uv run inspect eval sanity-bench/run.py --model openai-api/local/your-model

# Run a specific sanity-bench category
uv run inspect eval sanity-bench/run.py@coding --model openai-api/local/your-model

# Run reporeason-bench
uv run inspect eval reporeason-bench/run.py --model openai-api/local/your-model
```

## Dependencies

- `inspect-ai >= 0.3.217`
- `inspect-evals[all,ifeval,scicode,terminal-bench-2] >= 0.10.0`
- `inspect-cyber >= 0.1.0`
- `instruction-following-eval >= 0.1.0`
- `openai >= 2.26.0`

## License

MIT
