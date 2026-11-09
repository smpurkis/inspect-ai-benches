# GOD-Bench Baseline Results

Raw Harbor job directories are retained under `jobs/`. Each directory contains
the job-level result and log plus per-task results, trial logs, agent output, and
published artifacts.

## Corrected Test Regrade (2026-07-31)

All 80 preserved candidate artifacts were regraded in isolated, offline
containers after correcting task and verifier defects. No model inference was
rerun, and the original Harbor job directories and `result.json` files remain
unchanged as raw evidence.

Machine-readable candidate paths, candidate hashes, test-input hashes, exact
public/hidden counts, and infrastructure status are retained in
`regrade-20260731-systems.json`, `regrade-20260731-data.json`,
`regrade-20260731-algorithms.json`, and `regrade-20260731-compilers.json`.

| Model | Original | Corrected | Summed agent execution | Benchmark wall time |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.6-35B-A3B-MTP-Q8_0-thinking | 1/20 | 1/20 | 2h 36m 26s | 3h 2m 13s |
| Qwen3.5-122B-A10B-MTP-UD-Q4_K_XL-thinking | 2/20 | 3/20 | 2h 28m 6s | 2h 45m 4s |
| gemma-4-31B-it-qat-UD-Q4_K_XL-thinking | 4/20 | 5/20 | 6h 21m 9s | 6h 48m 11s |
| Qwen3.6-27B-MTP-UD-Q8_K_XL-thinking | 7/20 | 6/20 | 18h 40m 47s | 21h 3m 49s across two job segments |

Corrections affecting scores:

- `bitemporal-entitlement` hidden verification now starts its own PostgreSQL
  instance. Qwen3.5-122B, Gemma4-31B, and Qwen3.6-27B pass; Qwen3.6-35B fails.
- `aligned-reallocator` now builds from `/app/files` and checks handle validation
  before alignment validation. All four candidates fail.
- `rust-python-pyo3` now checks a coupled matrix at subnormal scale. The previous
  Qwen3.6-27B pass fails.
- `wasm-lz77` now checks an exact 8 MiB incompressible input using the declared
  120-second timeout. The previous Qwen3.6-27B pass times out and fails.

Corrected passing tasks:

- Qwen3.6-35B: `physics-2d`.
- Qwen3.5-122B: `bitemporal-entitlement`, `msgpack-incremental`, `physics-2d`.
- Gemma4-31B: `bitemporal-entitlement`, `physics-2d`, `pkcs7-unpad`,
  `robust-orient2d`, `samscript-bootstrap`.
- Qwen3.6-27B: `async-cache-generation`, `bitemporal-entitlement`, `physics-2d`,
  `robust-orient2d`, `samscript-wasi`, `wasm-compression-wat`.

## Qwen3.6-35B-A3B-MTP-Q8_0-thinking

- Date: 2026-07-27
- Agent: `common.harbor_cli_agents:GodBenchPi` (Pi 0.73.1)
- Endpoint: llama-swap on port 8234
- Tasks: 20, one attempt each, concurrency 1
- Runtime: 3h 2m 13s
- Correctness: 1/20 (5%); `physics-2d` passed
- Harbor errors: 0
- Within budget: 9/20; the passing task exceeded its budget
- Efficiency: 0.031040204132090115 mean; 0.6208040826418023 on the pass
- Fresh input tokens: 354,290
- Cached input tokens: 15,574,622
- Output tokens: 351,909
- Weighted tool cost: 663
- Valid usage telemetry: 20/20
- Raw results and outputs:
  `jobs/compact-pi-qwen36-35b-thinking-20260727/`

`samscript-wasi` accounted for 14,523,907 model tokens, including 14,236,255
cached input tokens, and did not pass.

## Qwen3.5-122B-A10B-MTP-UD-Q4_K_XL-thinking

- Date: 2026-07-27
- Agent: `common.harbor_cli_agents:GodBenchPi` (Pi 0.73.1)
- Endpoint: llama-swap on port 8234
- Tasks: 20, one attempt each, concurrency 1
- Runtime: 2h 45m 4s
- Correctness: 2/20 (10%); `msgpack-incremental` and `physics-2d` passed
- Harbor errors: 0
- Within budget: 12/20; both passing tasks exceeded their budgets
- Efficiency: 0.07341387535845242 mean; 1.4682775071690486 summed
  across the two passes
- Fresh input tokens: 199,680
- Cached input tokens: 7,745,121
- Output tokens: 170,664
- Weighted tool cost: 615
- Valid usage telemetry: 20/20
- Raw results and outputs:
  `jobs/compact-pi-qwen35-122b-thinking-20260727/`

`wasm-compression-wat` accounted for 6,259,500 model tokens, including
6,150,194 cached input tokens, and did not pass.

## gemma-4-31B-it-qat-UD-Q4_K_XL-thinking

- Date: 2026-07-29
- Agent: `common.harbor_cli_agents:GodBenchPi` (Pi 0.73.1)
- Endpoint: llama-swap on port 8234
- Tasks: 20, one attempt each, concurrency 1
- Runtime: 6h 48m 11s
- Correctness: 4/20 (20%); `physics-2d`, `pkcs7-unpad`,
  `robust-orient2d`, and `samscript-bootstrap` passed
- Harbor errors: 0
- Within budget: 5/20; `pkcs7-unpad` and `samscript-bootstrap` were
  budget-compliant passes
- Efficiency: 0.1941328045876152 mean; 3.882656091752304 summed across the
  four passes
- Fresh input tokens: 581,496
- Cached input tokens: 10,846,492
- Output tokens: 391,319
- Weighted tool cost: 736
- Valid usage telemetry: 20/20
- Raw results and outputs:
  `jobs/compact-pi-gemma4-31b-thinking-20260729/`

`wasm-compression-wat` accounted for 5,105,963 model tokens, including
4,877,459 cached input tokens, and did not pass.

## Qwen3.6-27B-MTP-UD-Q8_K_XL-thinking

- Date: 2026-07-30 to 2026-07-31
- Agent: `common.harbor_cli_agents:GodBenchPi` (Pi 0.73.1)
- Endpoint: llama-swap on port 8234
- Tasks: 20, one attempt each, concurrency 1; completed across an interrupted
  12-task job and an 8-task continuation job
- Correctness: 7/20 (35%); `async-cache-generation`, `physics-2d`,
  `robust-orient2d`, `rust-python-pyo3`, `samscript-wasi`,
  `wasm-compression-wat`, and `wasm-lz77` passed
- Harbor errors: 0
- Within budget: 9/20; `physics-2d` was the only budget-compliant pass
- Efficiency: 0.14555237581254305 mean; 2.911047516250861 summed across the
  passes
- Fresh input tokens: 485,239
- Cached input tokens: 32,128,828
- Output tokens: 563,851
- Weighted tool cost: 957
- Valid usage telemetry: 19/20
- Raw results and outputs:
  `jobs/compact-pi-qwen36-27b-thinking-20260730/` and
  `jobs/compact-pi-qwen36-27b-thinking-20260730-continuation/`

`rust-python-pyo3` passed after 10h 35m of agent execution. Harbor recorded
16,713,678 input tokens, including 16,552,993 cached tokens, and 208,540 output
tokens, but its verifier usage artifact was invalid; its efficiency is therefore
zero and it is not a budget-compliant pass.
