#!/usr/bin/env python3
"""Step 3 hidden tests: thorough report validation."""

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
REPORT_SCRIPT = Path("/app/step_3/files/audit_report.py")
REPORT_PATH = Path("/app/step_3/files/report.txt")
MIGRATE_SCRIPT = Path("/app/step_1/files/migrate.py")
ETL_SCRIPT = Path("/app/step_2/files/etl.py")
DB_PATH = "/tmp/bench.db"


def _run_report() -> None:
    result = subprocess.run(
        [sys.executable, str(REPORT_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"audit_report.py failed:\n{result.stderr}"


def _run_etl() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    result = subprocess.run(
        [sys.executable, str(ETL_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ETL failed:\n{result.stderr}"


def test_hidden_cohort_retention_correct() -> None:
    """Cohort retention section is present with correct structure and values.

    All orders are in 2024-02, so only one cohort row should appear.
    The cohort has 20 distinct users (all users ordered in Feb 2024).
    There is no 2024-03 data, so retained count = 0.
    """
    _run_report()
    content = REPORT_PATH.read_text()
    assert "--- Cohort Retention ---" in content, "Missing Cohort Retention section"

    # Extract the cohort section
    cohort_section = content.split("--- Cohort Retention ---")[1].split("---")[0]
    assert "2024-02" in cohort_section, (
        "Expected 2024-02 cohort row in retention section"
    )
    # The section should show user count for 2024-02
    # All 20 users have at least one order in Feb 2024 based on the data
    lines = [l.strip() for l in cohort_section.strip().split("\n") if l.strip()]
    # At least the header and one data row
    data_lines = [l for l in lines if "2024-02" in l]
    assert len(data_lines) >= 1, (
        f"Expected at least one cohort data row for 2024-02, got: {lines}"
    )


def test_hidden_rolling_avg_exact() -> None:
    """Rolling revenue average section has correct format AND specific values.

    Required line format: 'YYYY-MM-DD  $X.XX'  (two spaces, dollar sign, 2dp)
    Known correct values:
      2024-02-01  $637.83   (only day in 30-day window on 2024-02-01)
      2024-02-11  $610.52   (all 11 order days included, total / 11 days)
    """
    _run_report()
    content = REPORT_PATH.read_text()
    assert "--- Rolling Revenue" in content, "Missing Rolling Revenue section"

    rolling_section = content.split("--- Rolling Revenue")[1]
    if "---" in rolling_section:
        rolling_section = rolling_section.split("---")[0]

    # Every data line must match strict format
    data_lines = [l for l in rolling_section.split("\n")
                  if re.match(r"^\d{4}-\d{2}-\d{2}", l.strip())]
    assert len(data_lines) > 0, (
        f"No date lines found in Rolling Revenue section:\n{rolling_section}"
    )
    bad_format = []
    for line in data_lines:
        line = line.strip()
        if not re.match(r"^\d{4}-\d{2}-\d{2}  \$\d+\.\d{2}$", line):
            bad_format.append(line)
    assert not bad_format, (
        "Rolling Revenue lines do not match required format 'YYYY-MM-DD  $X.XX':\n"
        + "\n".join(bad_format)
    )

    # Verify specific known values
    lines_by_date = {}
    for line in data_lines:
        line = line.strip()
        parts = line.split("  ")
        if len(parts) == 2:
            lines_by_date[parts[0]] = parts[1]

    assert "2024-02-01" in lines_by_date, "Missing row for 2024-02-01"
    assert lines_by_date["2024-02-01"] == "$637.83", (
        f"2024-02-01 rolling avg: expected $637.83, got {lines_by_date['2024-02-01']}"
    )
    assert "2024-02-11" in lines_by_date, "Missing row for 2024-02-11"
    assert lines_by_date["2024-02-11"] == "$610.52", (
        f"2024-02-11 rolling avg: expected $610.52, got {lines_by_date['2024-02-11']}"
    )


def test_hidden_report_contains_expected_strings() -> None:
    """Report contains known correct values from the CDC-modified dataset.

    Verifies specific expected strings that a correct implementation must produce:
    - Total Revenue: $6715.72 (sum of 93 orders after CDC)
    - Total Orders: 93
    - Active Users: 17
    - Total Products: 28 (30 original minus 2 CDC deletes)
    - Top product: Tool Advanced (highest revenue after CDC updates)
    """
    _run_report()
    content = REPORT_PATH.read_text()

    assert "Total Revenue: $6715.72" in content, (
        f"Expected 'Total Revenue: $6715.72' not found. Check CDC processing."
    )
    assert "Total Orders: 93" in content, (
        f"Expected 'Total Orders: 93' not found. Check CDC delete cascade."
    )
    assert "Active Users: 17" in content, (
        f"Expected 'Active Users: 17' not found."
    )
    assert "Total Products: 28" in content, (
        f"Expected 'Total Products: 28' not found. Check CDC deletes."
    )
    # Tool Advanced should appear in top products (highest revenue after CDC)
    assert "Tool Advanced" in content, (
        f"Expected 'Tool Advanced' in report (top product by revenue after CDC)."
    )


def test_hidden_cohort_exact_row() -> None:
    """Cohort retention section contains the exact row for 2024-02.

    All 93 orders are in February 2024 (20 distinct users placed orders).
    There are no March 2024 orders, so retained count must be 0 (0.0%).
    Required row format: '2024-02     20      0 (0.0%)'
    """
    _run_report()
    content = REPORT_PATH.read_text()
    assert "--- Cohort Retention ---" in content, "Missing Cohort Retention section"

    cohort_section = content.split("--- Cohort Retention ---")[1].split("---")[0]

    # Must contain a line that covers: 2024-02, 20 users, 0 retained, 0.0%
    lines = cohort_section.strip().split("\n")
    feb_lines = [l for l in lines if "2024-02" in l]
    assert feb_lines, f"No 2024-02 row found in cohort section:\n{cohort_section}"

    feb_line = feb_lines[0].strip()
    # Check the essential values are present
    assert "20" in feb_line, (
        f"2024-02 cohort should have 20 distinct users, got: {feb_line!r}"
    )
    assert "0 (0.0%)" in feb_line or "0    (0.0%)" in feb_line or "0 (0.0" in feb_line, (
        f"2024-02 retained count should be 0 (0.0%), got: {feb_line!r}"
    )


REFERENCE_REPORT_SHA256 = "442e31a1210687db32772b4b2fcf7eeff2e9e10042a4c2b7122526ad06d0f0c8"


def test_hidden_report_byte_exact() -> None:
    """report.txt must be byte-for-byte identical to the hidden reference.

    SHA-256 of the correct report: 442e31a1210687db32772b4b2fcf7eeff2e9e10042a4c2b7122526ad06d0f0c8

    This test catches any formatting deviation: wrong spacing, wrong decimal
    precision, wrong section order, wrong values, or missing trailing newline.
    """
    import hashlib
    _run_report()
    actual_bytes = REPORT_PATH.read_bytes()
    actual_sha = hashlib.sha256(actual_bytes).hexdigest()
    assert actual_sha == REFERENCE_REPORT_SHA256, (
        f"report.txt SHA-256 mismatch.\n"
        f"  got:      {actual_sha}\n"
        f"  expected: {REFERENCE_REPORT_SHA256}\n\n"
        "Every byte must match the reference. Check:\n"
        "  - Rolling Revenue lines format: 'YYYY-MM-DD  $X.XX' (two spaces)\n"
        "  - Cohort Retention row: '2024-02     20      0 (0.0%)'\n"
        "  - Section separators are blank lines (not extra spaces)\n"
        "  - File ends with a single trailing newline"
    )


def test_hidden_report_from_fresh_db() -> None:
    """Report generated from a clean rebuild (ETL + report) has correct totals."""
    _run_etl()
    _run_report()
    content = REPORT_PATH.read_text()
    assert "Total Revenue: $6715.72" in content, (
        "Report from fresh ETL rebuild has wrong total revenue"
    )
    assert "Total Orders: 93" in content, (
        "Report from fresh ETL rebuild has wrong order count"
    )


def test_hidden_report_ordering() -> None:
    """Top Products section is ordered by revenue descending, ties broken by name."""
    _run_report()
    content = REPORT_PATH.read_text()

    assert "--- Top Products ---" in content, "Missing Top Products section"
    products_section = content.split("--- Top Products ---")[1]
    # Cut at next section
    if "---" in products_section:
        products_section = products_section.split("---")[0]

    # Extract dollar amounts from the top products lines
    dollar_amounts = re.findall(r"\$(\d+\.\d{2})", products_section)
    if len(dollar_amounts) >= 2:
        revenues = [float(a) for a in dollar_amounts]
        assert revenues == sorted(revenues, reverse=True), (
            f"Top Products not sorted by revenue descending: {revenues}"
        )

    # Tool Advanced should appear before Gadget Plus (higher revenue)
    if "Tool Advanced" in products_section and "Gadget Plus" in products_section:
        pos_tool = products_section.index("Tool Advanced")
        pos_gadget = products_section.index("Gadget Plus")
        assert pos_tool < pos_gadget, (
            "Tool Advanced ($599.96) should appear before Gadget Plus ($559.93)"
        )


def test_hidden_query_plan_reasonable() -> None:
    """Critical queries use indexes (don't full-scan on large joins)."""
    _run_report()
    conn = sqlite3.connect(DB_PATH)

    # Check that the orders query on product_id uses an index
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT COUNT(*), SUM(total) FROM orders WHERE product_id = 1"
    ).fetchall()
    plan_text = " ".join(str(r) for r in plan)
    assert (
        "idx_orders_product_id" in plan_text
        or "USING INDEX" in plan_text
        or "SEARCH" in plan_text
    ), f"Query on orders.product_id might not use index. Plan: {plan_text}"

    # Check that the orders query on user_id uses an index
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT COUNT(*), SUM(total) FROM orders WHERE user_id = 1"
    ).fetchall()
    plan_text = " ".join(str(r) for r in plan)
    assert (
        "idx_orders_user_id" in plan_text
        or "USING INDEX" in plan_text
        or "SEARCH" in plan_text
    ), f"Query on orders.user_id might not use index. Plan: {plan_text}"

    conn.close()


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
