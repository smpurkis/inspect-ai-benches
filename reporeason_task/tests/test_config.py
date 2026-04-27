"""Verbose tests for config helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import config


def test_runs_root_and_ensure_runs_root(tmp_path: Path) -> None:
    original_workspace = config.WORKSPACE_DIR
    try:
        config.WORKSPACE_DIR = tmp_path / "workspace"
        runs_root = config.runs_root()
        assert runs_root == config.WORKSPACE_DIR / "runs"
        created = config.ensure_runs_root()
        assert created.exists()
        assert created == runs_root
    finally:
        config.WORKSPACE_DIR = original_workspace


def test_load_config_returns_empty_for_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    assert config.load_config(missing) == {}


def test_load_config_reads_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm_judge:\n  enabled: true\n", encoding="utf-8")
    loaded = config.load_config(config_path)
    assert loaded.get("llm_judge", {}).get("enabled") is True


def test_llm_judge_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "load_config", lambda *args, **kwargs: {})
    settings = config.llm_judge_config()
    assert settings["enabled"] is False
    assert settings["base_url"] == ""
    assert settings["api_key"] == ""
    assert settings["model"] == ""


def test_llm_judge_config_reads_values(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "llm_judge": {
            "enabled": True,
            "base_url": "https://example.test",
            "api_key": "secret",
            "model": "gpt-test",
        }
    }
    monkeypatch.setattr(config, "load_config", lambda *args, **kwargs: payload)
    settings = config.llm_judge_config()
    assert settings["enabled"] is True
    assert settings["base_url"] == "https://example.test"
    assert settings["api_key"] == "secret"
    assert settings["model"] == "gpt-test"
