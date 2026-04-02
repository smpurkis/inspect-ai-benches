# RepoReason Benchmark

**A precision benchmark for repo-reasoning models, built on [Inspect AI](https://inspect.ai).**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/) [![Docker](https://img.shields.io/badge/Docker-required-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/) [![License](https://img.shields.io/badge/License-MIT-3b82f6?style=for-the-badge)](LICENSE)

RepoReason clones upstream repos at fixed commits, masks a single assertion in
the test suite, and asks a model to fill in the `<blank>` placeholder. Scoring
is exact-match with an optional LLM equivalence judge for near-miss answers.

## Two evaluation modes

| Task file | Entry point | How it works |
|-----------|-------------|-------------|
| `src/reporeason_native.py` | `reporeason_native` | Docker sandbox + native `bash` tool — model explores the repo itself |
| `src/reporeason_opencode.py` | `reporeason` | OpenCode agent — launches an OpenCode instance that explores the repo |

Both share the same Jinja2 prompt templates (`src/prompts/`), JSON parser
(`src/parsing.py`), and scorer with LLM judge (`src/scoring.py`).

## Quick start

```bash
# Install dependencies
uv sync          # or: pip install -e .

# Native task (sandbox bash tool)
uv run inspect eval src/reporeason_native.py \
  --model openai-api/local/DeepSeek-V3-0324 \
  --env LOCAL_BASE_URL="https://YOUR_ENDPOINT/openai/v1/" \
  --env LOCAL_API_KEY="YOUR_KEY" \
  --limit 5

# OpenCode task
OPENCODE_PROVIDER=openai-custom-endpoint uv run inspect eval src/reporeason_opencode.py \
  --model openai-api/local/gpt-5.2 \
  --env LOCAL_BASE_URL="https://YOUR_ENDPOINT/openai/v1/" \
  --env LOCAL_API_KEY="YOUR_KEY" \
  --limit 5
```

## How it works

```
datasets/consistent_dataset.yaml
   │
   ▼
clone repo @ commit → mask assertion → solver (bash / OpenCode) → JSON answer
                                              │
                                              ▼
                                    parse + score + LLM judge
```

1. Each dataset entry provides a repo URL, commit hash, and masked assertion.
2. The repo is cloned and the mask applied (inside a Docker sandbox for native,
   or on the host for OpenCode).
3. The solver explores the codebase and returns `{ "reason": ..., "answer": ... }`.
4. The scorer checks exact match; on miss, an optional LLM judge decides equivalence.

## Repository layout

```
.
├── src/
│   ├── reporeason_native.py     # Inspect AI task — native sandbox
│   ├── reporeason_opencode.py   # Inspect AI task — OpenCode agent
│   ├── config.py                # Paths, port base, LLM judge config
│   ├── opencode_client.py       # Docker-backed OpenCode client
│   ├── parsing.py               # Robust JSON extraction
│   ├── scoring.py               # Inspect AI scorer + LLM judge
│   ├── readonly_approver.py     # Approval policy (read-only bash)
│   ├── prompts/
│   │   ├── __init__.py          # Jinja2 template loader
│   │   ├── task_instructions.j2 # Task prompt template
│   │   └── judge_equivalence.j2 # LLM judge prompt template
│   └── compose.native.yaml      # Docker Compose for native sandbox
├── tests/
├── datasets/
│   ├── dataset.yaml
│   └── consistent_dataset.yaml
├── docker-compose.yml
├── dockerfile
├── pyproject.toml
└── config.yaml
```

## Requirements

- Python 3.11+
- Docker (for sandboxes / OpenCode workers)
- `git` on PATH
- Network access to clone upstream repos

## Configuration

Optional overrides via `config.yaml` and environment variables:

```yaml
llm_judge:
  enabled: true
  base_url: "https://your-endpoint.openai.azure.com/openai/v1/"
  api_key: "${OPENAI_API_KEY}"
  model: "gpt-5.2"
```

Key environment variables:

| Variable | Purpose |
|----------|---------|
| `LOCAL_BASE_URL` | Model endpoint URL |
| `LOCAL_API_KEY` | Model API key |
| `OPENCODE_PROVIDER` | OpenCode provider override (`openai-custom-endpoint`, `openai-custom-endpoint`) |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` | LLM judge config |

## Dataset format

```yaml
- repo_url: https://github.com/org/repo.git
  repo_commit_id: deadbeef...
  mask:
    file: tests/test_example.py
    assertion_statement: "assert foo == 3"
    masked_statement: "assert foo == <blank>"
    answer: "3"
```

`answer` can be a string or list of acceptable strings.

## Testing

```bash
uv run python -m pytest tests/ -v
```

## Troubleshooting

- **Docker not running**: ensure `docker info` works.
- **Port conflicts**: adjust `OPENCODE_PORT_BASE` env or limit `--max-connections`.
- **Clone failures**: verify network access and repo URLs in the dataset.

## Credit

Inspired by the ideas in https://www.arxiv.org/abs/2601.03731.
Not affiliated with the authors of that paper.
