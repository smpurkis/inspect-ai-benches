# GOD-Bench

GOD-Bench is a native [Harbor](https://github.com/harbor-framework/harbor)
dataset. Inspect AI is not part of its execution path.

## Setup

```bash
cd god-bench
uv sync
```

## Run

`run-local.sh` targets the model currently served by llama-swap at
`http://127.0.0.1:8234/v1` and stores native jobs under `jobs/`:

```bash
./run-local.sh --tasks physics-fix --rounds 1 --parallel 1
```

It defaults to `Qwen3.8-Flash-Next-Gufo-Gyro-M-Stream`; override with
`GOD_BENCH_MODEL`, `GOD_BENCH_BASE_URL`, and `GOD_BENCH_API_KEY`. You can also
invoke the runner directly:

```bash
uv run python run.py \
  --model Qwen3.8-Flash-Next-Gufo-Gyro-M-Stream \
  --base-url http://127.0.0.1:8234/v1 \
  --api-key local \
  --tasks physics-fix,wasm-lz77,samscript-wasi \
  --parallel 1
```

For the `pi` and `opencode` agents the runner rewrites `127.0.0.1`/`localhost`
to `172.17.0.1` so Harbor containers can reach the host endpoint.

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
