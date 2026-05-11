# sanity-bench

A small, token-efficient evaluation suite to get a quick "feel" for how an LLM behaves across many capability axes. No Docker, no inspect-ai overhead — just one HTTP call per task to an OpenAI-compatible endpoint and a deterministic score.

## Why this exists

god-bench is high-fidelity but burns 5-20M+ tokens and 50-125 minutes per task per model. That's the wrong tool for "should I use this local model?" sanity checks. sanity-bench targets the same conceptual coverage with ~256-2048 output tokens per task and a few minutes total wall time per model.

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
- `structured_output` — emit valid JSON matching a schema
- `safety` — appropriate refusal + appropriate non-refusal

## Run

```bash
cd inspect-ai-benches
LOCAL_BASE_URL=http://localhost:8234/v1 \
LOCAL_API_KEY=purkis-home-blah \
uv run python sanity-bench/run.py \
  --model Qwen3.6-27B-MTP-Q8_0-thinking \
  --parallel 4
```

Useful flags:

- `--categories math,reasoning` — restrict to a subset
- `--tasks math-01,reasoning-03` — pin specific tasks
- `--rounds N` — repeat each task N times for averaging
- `--judge-model NAME` — override which model judges open-ended responses (default = same as `--model`)
- `--log-dir DIR` — where per-run sidecars + report land (default `logs/sanity/<model>/`)

## Output

Each task drops a `<task-id>.json` sidecar with prompt, response, score, and token usage. A final `report.txt` shows the per-category table.

## Adding tasks

Tasks live in `tasks/<category>.yaml` (one file per category). Schema in `schema.md`.

## Scoring

Most tasks are scored deterministically (regex / exact-match / code-exec / JSON-schema). A small number of open-ended creative or research prompts use LLM-as-judge against a rubric — these are tagged `scoring.type: judge` and add one extra call per task.
