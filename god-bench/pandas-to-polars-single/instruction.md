Repair `normalization.py`, the only editable file. Implement lazy v2 normalization and a first-match quarantine split exactly as specified in `TASK.md`; the supplied CLI and analytics are not candidate work.

Keep both results lazy, preserve source values in quarantine, parse offset timestamps as UTC instants, retain optional text nulls, and emit exact columns and deterministic ordering. Work offline without pandas or eager Polars reads. Run `python3 -m pytest -q /app/files/tests.py`.
