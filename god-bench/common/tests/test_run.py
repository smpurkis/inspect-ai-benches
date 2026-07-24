from __future__ import annotations

import importlib.util
from pathlib import Path


RUN_PATH = Path(__file__).resolve().parents[2] / "run.py"
SPEC = importlib.util.spec_from_file_location("god_bench_run", RUN_PATH)
assert SPEC is not None and SPEC.loader is not None
RUN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN)


def test_container_base_url_translates_loopback_only():
    assert (
        RUN._container_base_url("http://127.0.0.1:8234/v1")
        == "http://172.17.0.1:8234/v1"
    )
    assert RUN._container_base_url("https://models.example/v1") == "https://models.example/v1"


def test_prepare_cli_tasks_changes_only_phase_networking(tmp_path):
    RUN._prepare_cli_tasks(["pandas-to-polars-single"], tmp_path)

    config = (tmp_path / "pandas-to-polars-single" / "task.toml").read_text()
    assert '[environment]\nnetwork_mode = "public"' in config
    assert '[verifier]\nnetwork_mode = "no-network"' in config
    assert "timeout_sec = 10800.0" in config
    assert (tmp_path / "pandas-to-polars-single" / "files" / "contract.toml").is_file()
