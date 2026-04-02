#!/usr/bin/env python3
"""Step 3 visible tests: verify audit report generation."""

import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORT_SCRIPT = BASE / "audit_report.py"
REPORT_PATH = BASE / "report.txt"


def _run_report() -> None:
    """Run the audit report script."""
    result = subprocess.run(
        [sys.executable, str(REPORT_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"audit_report.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_report_generated() -> None:
    """Report file exists at expected path and has meaningful content."""
    _run_report()
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    content = REPORT_PATH.read_text()
    assert len(content) > 200, f"Report seems too short (len={len(content)})"


def test_report_header() -> None:
    """Report contains the correct header and generated timestamp."""
    _run_report()
    content = REPORT_PATH.read_text()
    assert "=== SALES AUDIT REPORT ===" in content, "Missing report header"
    assert "Generated: 2024-03-01" in content, "Missing or incorrect generated timestamp"


def test_report_has_required_sections() -> None:
    """All 4 required section headers are present."""
    _run_report()
    content = REPORT_PATH.read_text()
    required_sections = [
        "--- Summary ---",
        "--- Top Products ---",
        "--- Cohort Retention ---",
        "--- Rolling Revenue",
    ]
    for section in required_sections:
        assert section in content, f"Missing section: {section!r}"


def test_report_summary_totals() -> None:
    """Summary section contains correct aggregate values."""
    _run_report()
    content = REPORT_PATH.read_text()
    assert "Total Users: 20" in content, "Total Users should be 20"
    assert "Total Orders:" in content, "Missing Total Orders line"
    assert "Total Revenue: $" in content, "Missing Total Revenue line"


def test_report_deterministic() -> None:
    """Two successive runs produce identical report.txt."""
    _run_report()
    report1 = REPORT_PATH.read_text()
    _run_report()
    report2 = REPORT_PATH.read_text()
    assert report1 == report2, "Report is not deterministic: two runs produced different output"


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
