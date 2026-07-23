# GOD-Bench

GOD-Bench is a native [Harbor](https://github.com/harbor-framework/harbor)
dataset. Inspect AI is not part of its execution path.

## Setup

```bash
cd god-bench
uv sync
```

## Run

The runner streams Harbor progress and stores native jobs under `jobs/`:

```bash
uv run python run.py \
  --model Qwen3.6-35B-A3B-MTP-Q8_0-instruct \
  --base-url http://127.0.0.1:8234/v1 \
  --api-key "$OPENAI_API_KEY" \
  --tasks physics-2d,wasm-lz77,samscript-wasi \
  --parallel 1
```

The runner supplies Harbor with:

- `common.harbor_agent:GodBenchAgent`
- `common.harbor_verifier:GodBenchVerifier`
- the active task directories containing `task.toml`

Use Harbor's live results viewer with:

```bash
uv run harbor view jobs
```

Regenerate the correctness-first report without running models:

```bash
uv run python run.py --report-only
```

## Isolation

Every active task is offline. Harbor runs the agent and verifier in separate
containers. The verifier reconstructs pristine visible files, overlays only
contract-editable artifacts, injects hidden tests, and emits binary correctness
plus efficiency metrics in native Harbor `result.json` files.
