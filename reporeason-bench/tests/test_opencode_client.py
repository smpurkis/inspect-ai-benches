"""Verbose tests for OpenCode client helpers."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.opencode_client import (
    OpenCodeClient,
    WorkerContext,
    _env_truthy,
    build_worker_context,
)


def test_worker_context_compose_env() -> None:
    ctx = WorkerContext(
        worker_id=1,
        port=5001,
        project_name="reporeason_01",
        repo_path=Path("/tmp/repo"),
        opencode_config=Path("/tmp/opencode.json"),
    )
    env = ctx.compose_env()
    assert env["HOST_PORT"] == "5001"
    assert env["REPO_MOUNT"] == str(Path("/tmp/repo").resolve())
    assert env["OPENCODE_CONFIG"] == "/tmp/opencode.json"
    assert env["COMPOSE_PROJECT_NAME"] == "reporeason_01"
    assert ctx.base_url == "http://0.0.0.0:5001"


def test_build_worker_context_assigns_port() -> None:
    ctx = build_worker_context(2, Path("/tmp/repo"), port=5555)
    assert ctx.port == 5555
    assert ctx.worker_id == 2
    assert "reporeason_02" in ctx.project_name


def test_env_truthy() -> None:
    with patch.dict(os.environ, {"TEST_TRUTHY": "true"}):
        assert _env_truthy("TEST_TRUTHY") is True
    with patch.dict(os.environ, {"TEST_TRUTHY": "0"}):
        assert _env_truthy("TEST_TRUTHY") is False


def test_client_requests() -> None:
    ctx = WorkerContext(
        worker_id=0,
        port=5000,
        project_name="reporeason_00",
        repo_path=Path("/tmp/repo"),
        opencode_config=Path("/tmp/opencode.json"),
    )
    client = OpenCodeClient(ctx)

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    with patch("src.opencode_client.requests.post") as post:
        post.return_value = FakeResponse({"id": "session-1"})
        with patch("src.opencode_client.time.sleep"):
            session = client.create_session("test")
        assert session["id"] == "session-1"

    with patch("src.opencode_client.requests.post") as post:
        post.return_value = FakeResponse({"parts": []})
        resp = client.send_message(
            "session-1", "prompt", model="provider/model", agent="plan"
        )
        assert resp == {"parts": []}
        args, kwargs = post.call_args
        assert "/session/session-1/message" in args[0]
        payload = kwargs.get("json")
        assert payload["model"]["providerID"] == "provider"
        assert payload["model"]["modelID"] == "model"
        assert payload["agent"] == "plan"

    with patch("src.opencode_client.requests.get") as get:
        get.return_value = FakeResponse([])
        messages = client.fetch_messages("session-1")
        assert messages == []


@pytest.mark.integration
def test_opencode_docker_roundtrip(tmp_path: Path) -> None:
    if os.getenv("OPENCODE_INTEGRATION") not in {"1", "true", "yes"}:
        pytest.skip("OPENCODE_INTEGRATION not enabled")
    model = os.getenv("OPENCODE_MODEL")
    if not model:
        pytest.skip("OPENCODE_MODEL not set")

    repo_root = tmp_path
    ctx = build_worker_context(0, repo_root, port=5858)
    client = OpenCodeClient(ctx)
    client.start()
    try:
        session = client.create_session("integration-test")
        resp = client.send_message(
            session["id"],
            'Respond with JSON: {"reason": "ok", "answer": "ok"}',
            model=model,
            agent="plan",
        )
        assert "parts" in resp
    finally:
        client.stop()
