# Compact pipeline contract

`TASK.md` defines the candidate normalization and quarantine kernel. The supplied
`pipeline_polars.py` scans `input_v2.parquet` and `merchants.parquet`, calls that
kernel, writes `normalized.parquet` and `quarantine.parquet`, and computes the
deterministic `analytics.json`. Candidate code performs no I/O or collection.

The CLI remains:

```text
python3 /app/files/pipeline_polars.py --in <input_dir> --out <output_dir>
```
