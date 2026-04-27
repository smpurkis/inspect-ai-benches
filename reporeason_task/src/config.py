"""Shared filesystem configuration used across the benchmark runner."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Primary input/output locations -------------------------------------------------
DATASET_PATH = PROJECT_ROOT / "datasets" / "consistent_dataset.yaml"
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
RESULTS_DIR = PROJECT_ROOT / "results"
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# Docker / OpenCode wiring -------------------------------------------------------
OPENCODE_CONFIG_PATH = PROJECT_ROOT / "opencode.json"
DOCKER_COMPOSE_FILE = PROJECT_ROOT / "docker-compose.yml"
DOCKER_PROJECT_PREFIX = "reporeason"
DEFAULT_PORT_BASE = 5000


def runs_root() -> Path:
    """Location where temporary per-task repositories are cloned."""

    return WORKSPACE_DIR / "runs"


def ensure_runs_root() -> Path:
    path = runs_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: Path | None = None) -> dict:
    import os

    from yaml import safe_load

    env_path = os.getenv("CONFIG_PATH")
    config_path = path
    if config_path is None and env_path:
        config_path = Path(env_path)
    if config_path is None:
        config_path = CONFIG_PATH
    if config_path.is_dir() or not config_path.exists():
        return {}
    content = config_path.read_text(encoding="utf-8").strip()
    if not content:
        return {}
    loaded = safe_load(content)
    return loaded or {}


def llm_judge_config() -> dict[str, str | bool]:
    config = load_config()
    llm = config.get("llm_judge") if isinstance(config, dict) else {}
    if not isinstance(llm, dict):
        llm = {}
    return {
        "enabled": bool(llm.get("enabled", False)),
        "base_url": str(llm.get("base_url", "")),
        "api_key": str(llm.get("api_key", "")),
        "model": str(llm.get("model", "")),
    }
