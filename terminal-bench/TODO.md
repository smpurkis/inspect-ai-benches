# Terminal Bench — Task Review Progress

## Workflow
Go through each task alphabetically. For each: present structure (instructions, visible/hidden files, test breakdown), decide whether to adjust difficulty, then run benchmarks (gpt-4.1-mini and gpt-5) to verify. Tasks should NOT use multi-step gating.

Benchmark command:
```
cd /home/sam/projects/repos/llm-benchmark/inspect-ai-benches/terminal-bench && uv run inspect eval <task>/run.py --model openai-api/local/<model> --env LOCAL_BASE_URL="https://micha-m6kmcqwd-eastus2.cognitiveservices.azure.com/openai/v1/" --env LOCAL_API_KEY="4stjFlPbWUZYZvIP0EZ77O4AR6j42ab5Pko6isbMv2pISlgUkt6bJQQJ99BAACHYHv6XJ3w3AAAAACOGwozk" --limit 1 -T variant_names=default
```

Models to test: `gpt-4.1-mini`, `gpt-5`

## Completed
- [x] **cifar10-burn** — Reviewed, kept as-is
- [x] **distributed-log-reconstruction** — Reviewed, kept as-is
- [x] **ext4-recovery** — DELETED (multi-step gating)
- [x] **git-hooks** — DELETED (overlaps with git-leak-complex)
- [x] **cifar10-pytorch** — Hardened: 100KB model limit, 65%/63% acc thresholds, 2+2 anti-gaming tests. gpt-5 scored 0.75 (missed hidden acc by 0.0008 at 60% threshold)
- [x] **git-leak-complex** — Reviewed, kept as-is
- [x] **nbc-vm-go** (renamed from nim-vm-go) — Reviewed, kept as-is (mini=0.000, gpt-5=1.000)
- [x] **physics-fix** — Hardened: removed bug comments, removed trivial tests, subtle CCD sign bug, 6 tests. mini=0.000, gpt-5=0.833
- [x] **pokemon-battle-fix** — Hardened: removed BUG comments, added STAB first-type-only bug + hidden_04 test. 7 visible + 7 hidden = 14 tests. mini=0.857, gpt-5=1.000
- [x] **rust-python-ctypes** — Converted to match pyo3: same 9 linalg ops (matmul, cholesky, solve_spd, norm2, qr, eig_symmetric, svd, matrix_exp, solve_lstsq) in C+ctypes. 8 visible + 7 hidden = 15 tests mirroring pyo3. mini=0.429, gpt-5=1.000
- [x] **rust-python-pyo3** — Reviewed: 8 visible + 7 hidden = 15 tests. Removed unused environment/test_rustlinalg.py. mini=0.667, gpt-5=0.800
- [x] **pandas-to-polars-single** — Reviewed, kept as-is (mini=0.000, gpt-5=0.000, gpt-5.4-high=0.923)
- [x] **samscript-wasi** — Rewrote: interpreter removed, task is "write WASM compiler from spec". 8 visible + 8 hidden = 16 tests. Structural checks (call-graph BFS + data section scan) in both visible and hidden tests. mini=0.062, gpt-5=0.625 (wrote real compiler but can't handle complex hidden programs).
- [x] **physics-2d** — Hardened: added circle shapes (circle-rect, circle-circle collisions), reduced hidden tests from 90 to 30 hardest (20 gpt-5 failures + 10 hard passing), removed 3 unfair tests. 19 visible + 30 hidden = 49 tests. mini=0.000, gpt-5=0.612
- [x] **pokemon-sapphire-pyboy** — DELETED (mini=1.000, gpt-5=1.000, tests are mostly static analysis)
- [x] **wasm-lz77** — Reviewed: removed 2 free tool-existence tests. 15 visible + 10 hidden = 25 tests. Genuinely hard (WAT from scratch). mini=0.192, gpt-5=0.423
- [x] **text-pokemon-fix** — Removed BUG comments and hints. 6 visible + 6 hidden = 12 tests. mini=0.000, gpt-5=1.000 (bugs too easy even without hints).
- [x] **text-pokemon-rust** — DELETED (exact duplicate of text-pokemon-fix, no Rust despite name)
- [x] **samscript-bootstrap** — Rewrote: gave complete working interpreter (read-only in container), task is "write SamScript interpreter in SamScript". 8 visible + 8 hidden = 16 tests. Hidden tests use unseen programs + dynamic generation + exact f64 parity (spring mass, numerical methods). mini=0.188, gpt-5=0.562 (passed visible but hardcoded/pattern-matched, failed on hidden programs).
- [x] **nim-vm-fix** — Reviewed: 14 bugs across vm.nim/parser.nim/main.nim, 6 visible + 26 hidden = 32 tests. Reference src is stale (still has bugs). gpt-5 inconsistent (0.81–1.0), mini=0.000.
- [x] **wasm-compression-wat** — Hardened: added test.txt, 4 visible anti-cheat tests (QPX1 header, generated data roundtrip, small varied, size check), 8 hidden tests (no hardcoded paths, different-inputs-different-outputs, reverse cross-codec, binary/large/empty roundtrip, compression ratio, dict validation). 10 visible + 11 hidden = 21 tests. mini=0.000, gpt-5=0.048
- [x] **sql-migration-rebuild** — Hardened: replaced SQL reference with natural-language business requirements, reduced visible tests to 1 (migrations run), added misleading comments justifying each bug, added 3 new bugs (DEFAULT 0, missing NOT NULL, quantity>=0). 17 bugs total, 1 visible + 18 hidden = 19 tests. mini=0.263, gpt-5=0.947

## Not Yet Reviewed (alphabetical)

(none)

## Notes
- Scoring: accuracy = tests_passed / total_tests (partial credit)
- Files: `files/` → `/app/files/` in sandbox, `hidden/` → `/app/hidden/` only during scoring
- Don't use Docker bind mounts in inspect sandbox; use staged_eval.py injection instead
- Design principle: tasks should NOT be multi-step gated
