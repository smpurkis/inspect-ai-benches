from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

FILES = Path(__file__).resolve().parent
LUA = shutil.which("lua") or shutil.which("lua5.4")


def run_lua(body: str) -> list[str]:
    if LUA is None:
        pytest.skip("Lua 5.4 is not installed")
    prefix = f'package.path = "{FILES}/?.lua;" .. package.path\n'
    run = subprocess.run([LUA, "-"], input=prefix + body, text=True, capture_output=True, timeout=10)
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def test_normal_import_and_capability() -> None:
    lines = run_lua(r'''
local sources = {
  util = "local M = ...; M.double = function(x) return x * 2 end",
  main = "local M = ...; local u = require('util'); M.answer = u.double(cap.seed)",
}
local value = require("loader").new(sources, {seed = 21}):require("main")
print(value.answer)
''')
    assert lines == ["42"]


def test_edge_cycle_uses_stable_export_identity() -> None:
    lines = run_lua(r'''
local sources = {
  a = "local M = ...; M.name = 'a'; M.peer = require('b')",
  b = "local M = ...; M.name = 'b'; M.peer = require('a')",
}
local loader = require("loader").new(sources, {})
local a = loader:require("a")
print(a.peer.name, a.peer.peer == a, loader:require("a") == a)
''')
    assert lines == ["b\ttrue\ttrue"]


def test_sandbox_invariant_blocks_host_and_mutation() -> None:
    lines = run_lua(r'''
local source = [[
local M = ...
M.globals = (_G == nil and package == nil and io == nil and os == nil and debug == nil)
M.capwrite = not pcall(function() cap.secret = "changed" end)
M.libwrite = not pcall(function() math.pi = 0 end)
M.meta = getmetatable(cap)
]]
local value = require("loader").new({probe = source}, {secret = "safe"}):require("probe")
print(value.globals, value.capwrite, value.libwrite, value.meta)
''')
    assert lines == ["true\ttrue\ttrue\tread-only"]


def test_protected_runtime_is_deterministic() -> None:
    if LUA is None:
        pytest.skip("Lua 5.4 is not installed")
    scenario = r'''
return {
  sources = {main = "local M = ...; M.z = cap.n; M.a = {x = 'ok'}"},
  capabilities = {n = 7},
  requests = {"main", "main"},
}
'''
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "scenario.lua"
        path.write_text(scenario, encoding="utf-8")
        env = {**os.environ, "LUA_PATH": f"{FILES}/?.lua;;"}
        command = [LUA, str(FILES / "loader_runtime.lua"), str(path)]
        first = subprocess.run(command, text=True, capture_output=True, env=env, check=True)
        second = subprocess.run(command, text=True, capture_output=True, env=env, check=True)
    assert first.stdout == second.stdout
    assert first.stdout.count("ok\tmain") == 2
