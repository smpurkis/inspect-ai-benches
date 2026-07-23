Implement the TODOs in `pipeline_polars.py`; it is the only editable file.

Run `python3 /app/files/pipeline_polars.py --in <input_dir> --out <output_dir>`.
Match the pandas reference pipelines exactly for v1 and v2 inputs, including lazy Polars execution, quarantine precedence, schemas, ordering, nulls, UTC timestamps, and six-decimal numeric outputs.

The machine contract is `contract.toml`. Detailed semantics are authoritative in `pipeline_contract.md`; executable references are `pipeline_pandas.py`, `pipeline_pandas_advanced.py`, and `pipeline_pandas_v2.py`. Public expected artifacts are under `public_data/expected/`.

Work offline. Do not use pandas, eager `pl.read_*`, `to_pandas()`, or modify tests, specifications, references, or data.

Run `python3 -m pytest -q /app/files/tests.py`.
