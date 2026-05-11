# sanity-bench

A small, token-efficient evaluation suite to get a quick "feel" for how an LLM behaves across many capability axes. Built on top of [inspect-ai](https://inspect.aisi.org.uk/) so eval logs are first-class and `inspect view` works out of the box.

## Why this exists

god-bench is high-fidelity but burns 5–20M+ tokens and 50–125 minutes per task per model. That's the wrong tool for "should I use this local model?" sanity checks. sanity-bench targets the same conceptual coverage with ~256–1536 output tokens per task and a few minutes total wall time per model — no Docker, no per-task sandbox spin-up.

## Categories (10 tasks each, 130 total)

- `general_knowledge` — factual recall (history, science, geography, popular culture)
- `common_sense` — physical/social commonsense reasoning
- `math` — arithmetic and word problems through grade-school / early algebra
- `reasoning` — multi-step logic, deductions, lateral thinking
- `coding` — write a short Python function from a spec
- `coding_debug` — find/fix a bug in given code
- `agentic_coding` — single-turn "agent" tasks (plan, choose tools, write patch)
- `instruction_following` — IFEval-style verifiable constraints (length, format, keywords)
- `creative_writing` — short creative pieces with verifiable structural constraints
- `writing` — summarisation, rephrasing, tone shift
- `deep_research` — synthesise structured answers from given material
- `structured_output` — emit valid JSON / YAML / CSV / XML / Markdown table
- `safety` — appropriate refusal + appropriate non-refusal

## Run

Run a single category:

```bash
LOCAL_BASE_URL=http://localhost:8234/v1 LOCAL_API_KEY=secret \
  uv run inspect eval sanity-bench/run.py@math \
    --model openai-api/local/Qwen3.6-27B-MTP-Q8_0-thinking \
    --env LOCAL_BASE_URL=http://localhost:8234/v1 \
    --env LOCAL_API_KEY=secret \
    --max-connections 4
```

Run all 13 categories in one go (a single eval pass):

```bash
uv run inspect eval sanity-bench/run.py \
  --model openai-api/local/MODEL_NAME \
  --env LOCAL_BASE_URL=http://localhost:8234/v1 \
  --env LOCAL_API_KEY=secret \
  --max-connections 8 \
  --log-dir logs/sanity/MODEL_NAME
```

Useful inspect-ai flags:

- `sanity-bench/run.py@math sanity-bench/run.py@reasoning` — multiple categories (space-separated positional args)
- `--limit N` — run only the first N samples per task (great for first-pass tuning)
- `--epochs N` — repeat each sample N times for averaging
- `--max-connections N` — parallel in-flight requests
- `--log-dir DIR` — eval log destination (defaults to `logs/`)

View the eval logs:

```bash
uv run inspect view --log-dir logs/sanity/MODEL_NAME
```

## Adding tasks

Tasks live in `tasks/<category>.yaml` (one file per category). Schema in [`schema.md`](schema.md). Adding a new task is just appending a YAML block — no Python changes needed.

To add a **new category**, add `tasks/newcat.yaml` AND add a corresponding `@task` function in `run.py`:

```python
@task
def newcat() -> Task:
    return _build_task("newcat")
```

(The `@task` functions are explicit rather than dynamically registered because inspect-ai's loader uses AST parsing to discover tasks — only top-level `def`s decorated with `@task` are visible.)

## Scoring

`scoring.py` ships 13 deterministic scorers — exact, contains, regex, regex_number, multiple_choice, code_exec_python, json_schema, length_range, refusal, plus a `composite` that ANDs or means over sub-scorers. Each task declares its scorer in YAML and the inspect-ai-side `sanity_scorer()` (in `run.py`) dispatches based on the sample metadata.

`<think>...</think>` blocks are stripped from the response before scoring so the final answer is what counts. For thinking-model servers that surface chain-of-thought via a separate `reasoning_content` field, that text is captured and recorded in the eval log (`reasoning_chars` metadata) but does not contribute to the score.

## Files

```
sanity-bench/
├── README.md         this file
├── schema.md         per-task YAML schema + scoring types
├── run.py            13 @task functions + sanity_scorer dispatching to scoring.py
├── scoring.py        13 deterministic scorers (pure functions, no inspect-ai dep)
└── tasks/
    └── <category>.yaml × 13
```
