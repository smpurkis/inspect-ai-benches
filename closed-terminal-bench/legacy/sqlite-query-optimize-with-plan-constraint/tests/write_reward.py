import json
from pathlib import Path

ctrf = Path("/logs/verifier/ctrf.json")
reward = Path("/logs/verifier/reward.txt")

if not ctrf.exists():
    reward.write_text("0.0")
    raise SystemExit

data = json.loads(ctrf.read_text())
summary = data.get("summary") or data.get("results", {}).get("summary") or {}
passed = summary.get("passed", 0)
total = summary.get("tests", 0) or summary.get("total", 0)
ratio = passed / total if total else 0.0
bonus = 0.5 if passed == total and total > 0 else 0.0
score = 0.5 * ratio + bonus
reward.write_text(f"{score:.6f}")
