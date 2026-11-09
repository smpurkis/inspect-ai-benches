# Compact collision-kernel contract

`TASK.md` is authoritative for the two editable functions. The supplied engine
uses semi-implicit Euler, deterministic ascending body-pair order, rectangle SAT,
circle-circle contacts, wall contacts, Baumgarte correction, and six-decimal
JSONL output. Candidate code is responsible only for circle-versus-rotated-box
manifolds and one accumulated normal/friction impulse iteration.

The unchanged CLI is:

```text
python3 /app/files/physics2d.py --config <config.json> --output <output.jsonl> --steps <N>
```
