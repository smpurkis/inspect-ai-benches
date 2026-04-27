"""Docker-backed OpenCode client used by worker threads."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import time

import requests

from .config import (
    DOCKER_COMPOSE_FILE,
    DOCKER_PROJECT_PREFIX,
    OPENCODE_CONFIG_PATH,
    PROJECT_ROOT,
)


@dataclass
class WorkerContext:
    worker_id: int
    port: int
    project_name: str
    repo_path: Path
    opencode_config: Path

    def compose_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            {
                "HOST_PORT": str(self.port),
                "PORT": str(self.port),
                "OPCODE_PORT": str(self.port),
                "REPO_MOUNT": str(self.repo_path.resolve()),
                "OPENCODE_CONFIG": str(self.opencode_config),
                "COMPOSE_PROJECT_NAME": self.project_name,
            }
        )
        return env

    @property
    def base_url(self) -> str:
        return f"http://0.0.0.0:{self.port}"


def build_worker_context(
    index: int, repo_root: Path, *, port: int | None = None
) -> WorkerContext:
    from .config import DEFAULT_PORT_BASE

    project_slug = f"{DOCKER_PROJECT_PREFIX}_{index:02d}"
    assigned_port = port if port is not None else DEFAULT_PORT_BASE + index
    return WorkerContext(
        worker_id=index,
        port=assigned_port,
        project_name=f"{project_slug}",
        repo_path=repo_root,
        opencode_config=OPENCODE_CONFIG_PATH,
    )


def _run_compose(args: list[str], ctx: WorkerContext) -> None:
    cmd = ["docker", "compose", "-f", str(DOCKER_COMPOSE_FILE), *args]
    try:
        subprocess.run(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=ctx.compose_env(),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:  # pragma: no cover - safety
        raise RuntimeError(
            f"[worker-{ctx.worker_id}] docker compose {' '.join(args)} failed: {exc.stderr.decode().strip()}"
        ) from exc


def _env_truthy(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes"}


class OpenCodeClient:
    def __init__(self, ctx: WorkerContext):
        self.ctx = ctx

    def start(self) -> None:
        args = ["up", "--detach"]
        if _env_truthy("OPENCODE_BUILD"):
            args.append("--build")
        _run_compose(args, self.ctx)

    def stop(self) -> None:
        for args in (["kill"], ["down", "--remove-orphans", "--timeout", "5"]):
            try:
                _run_compose(args, self.ctx)
            except RuntimeError:
                continue

    def create_session(self, title: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if title:
            payload["title"] = title
        time.sleep(2)
        resp = requests.post(
            f"{self.ctx.base_url}/session",
            json=payload,
            timeout=3600,
        )
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self,
        session_id: str,
        prompt: str,
        *,
        model: str,
        agent: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "parts": [{"type": "text", "text": prompt}],
        }
        if model:
            provider, model_id = model.split("/", 1)
            payload["model"] = {"providerID": provider, "modelID": model_id}
        if agent:
            payload["agent"] = agent
        resp = requests.post(
            f"{self.ctx.base_url}/session/{session_id}/message",
            json=payload,
            timeout=3600,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch_messages(self, session_id: str) -> list[dict[str, Any]]:
        resp = requests.get(
            f"{self.ctx.base_url}/session/{session_id}/message",
            timeout=3600,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):  # pragma: no cover - defensive
            return []
        return data
