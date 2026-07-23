from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from budget import BudgetConfig, BudgetState, PolicyConfig, TaskConfig, TaskContract
from common.budgeted_tools import StrictToolRuntime
from common.tests.test_harbor_agent import MemoryEnvironment


def _runtime(environment):
    contract = TaskContract(
        task=TaskConfig(public_test="python3 -m pytest -q /app/files/tests.py", build="true"),
        policy=PolicyConfig(editable=("main.py",)),
        budget=BudgetConfig(),
    )
    return StrictToolRuntime(contract, BudgetState(contract.budget), environment)


def test_strict_tools_cache_reads_enforce_edits_and_charge_no_progress():
    async def exercise():
        env = MemoryEnvironment()
        env.files.update({
            "/app/files/main.py": b"value = 1\n",
            "/app/files/tests.py": b"def test_ok(): pass\n",
        })
        env.directories.add("/app/files")
        runtime = _runtime(env)
        first = await runtime.read("main.py", 1, 1)
        cached = await runtime.read("/app/files/main.py", 1, 1)
        denied = await runtime.edit("tests.py", "pass", "fail")
        edited = await runtime.edit("main.py", "value = 1", "value = 2")
        public = json.loads(await runtime.public_test())
        retry = await runtime.public_test()
        assert first == "value = 1\n"
        assert cached.startswith("Cached:")
        assert denied.startswith("DENIED:")
        assert edited.startswith("Edited main.py")
        assert public["passed"] == 1
        assert retry.startswith("DENIED: identical")
        assert runtime.budget.no_progress_retries == 1
        assert runtime.trace.events[-1].no_progress is True
        assert "ps -e -o pid=" in env.commands

    asyncio.run(exercise())


def test_tool_definitions_never_expose_unrestricted_command_input():
    runtime = _runtime(MemoryEnvironment())
    schemas = [definition.as_openai_tool() for definition in runtime.definitions()]
    assert {item["function"]["name"] for item in schemas} == {
        "strict_search", "strict_read", "strict_edit", "strict_build", "run_public_tests"
    }
    assert all("command" not in item["function"]["parameters"].get("properties", {}) for item in schemas)


def test_editable_artifact_publication_enforces_size_limit(monkeypatch):
    async def exercise():
        env = MemoryEnvironment()
        env.files["/app/files/main.py"] = b"too large"
        env.directories.add("/app/files")
        runtime = _runtime(env)
        monkeypatch.setattr("common.budgeted_tools.MAX_EDITABLE_ARTIFACT_BYTES", 3)

        with pytest.raises(RuntimeError, match="per-file size"):
            await runtime.publish_editables()

    asyncio.run(exercise())
