from __future__ import annotations

import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile

import pytest

FILES = Path("/app/files")
if not FILES.exists():
    FILES = Path(__file__).resolve().parents[1] / "files"
LUA = shutil.which("lua") or shutil.which("lua5.4")


def run_lua(body: str, *, timeout: int = 15) -> list[str]:
    if LUA is None:
        pytest.skip("Lua 5.4 is not installed")
    prefix = f'package.path = "{FILES}/?.lua;" .. package.path\n'
    run = subprocess.run([LUA, "-"], input=prefix + body, text=True, capture_output=True, timeout=timeout)
    assert run.returncode == 0, run.stderr
    return run.stdout.splitlines()


def lua_long_string(value: str) -> str:
    level = ""
    while f"]{level}]" in value:
        level += "="
    return f"[{level}[{value}]{level}]"


def test_generated_import_dags_have_exact_values_and_single_execution() -> None:
    rng = random.Random(0xC4A8A1)
    for size in (2, 5, 11, 23):
        dependencies: list[list[int]] = []
        expected: list[int] = []
        entries = []
        for index in range(size):
            deps = sorted(rng.sample(range(index), rng.randrange(min(index, 4) + 1))) if index else []
            dependencies.append(deps)
            value = index + 1 + sum(expected[dep] for dep in deps)
            expected.append(value)
            imports = " ".join(f"local d{dep} = require('m{dep}');" for dep in deps)
            terms = " + ".join([str(index + 1)] + [f"d{dep}.value" for dep in deps])
            source = f"local M = ...; cap.hit('m{index}'); {imports} M.value = {terms}"
            entries.append(f"m{index} = {lua_long_string(source)}")
        script = f'''
local counts = {{}}
local sources = {{{",".join(entries)}}}
local l = require("loader").new(sources, {{hit = function(name) counts[name] = (counts[name] or 0) + 1 end}})
local root = l:require("m{size - 1}")
local again = l:require("m{size - 1}")
local once = true
for name, count in pairs(counts) do if count ~= 1 then once = false end end
print(root.value, again == root, once)
'''
        assert run_lua(script) == [f"{expected[-1]}\ttrue\ttrue"]


def test_generated_cycles_preserve_identity_from_every_root() -> None:
    for size in (2, 3, 8, 17):
        entries = []
        for index in range(size):
            nxt = (index + 1) % size
            source = f"local M = ...; M.id = {index}; M.next = require('m{nxt}')"
            entries.append(f"m{index} = {lua_long_string(source)}")
        for root in (0, size // 2, size - 1):
            script = f'''
local l = require("loader").new({{{",".join(entries)}}}, {{}})
local first = l:require("m{root}")
local cursor = first
for _ = 1, {size} do cursor = cursor.next end
print(cursor == first, first.id, l:require("m{root}") == first)
'''
            assert run_lua(script) == [f"true\t{root}\ttrue"]


def test_failure_rolls_back_entire_new_subgraph_and_retry_is_clean() -> None:
    lines = run_lua(r'''
local hits, fail = {}, true
local sources = {
  leaf = "local M = ...; cap.hit('leaf'); M.value = 10",
  middle = "local M = ...; cap.hit('middle'); M.leaf = require('leaf'); if cap.fail() then error('boom') end",
  root = "local M = ...; cap.hit('root'); M.middle = require('middle')",
  prior = "local M = ...; cap.hit('prior'); M.value = 99",
}
local cap = {
  hit = function(name) hits[name] = (hits[name] or 0) + 1 end,
  fail = function() return fail end,
}
local l = require("loader").new(sources, cap)
local prior = l:require("prior")
local ok = pcall(function() l:require("root") end)
fail = false
local root = l:require("root")
print(ok, root.middle.leaf.value, hits.root, hits.middle, hits.leaf, hits.prior, l:require("prior") == prior)
''')
    assert lines == ["false\t10\t2\t2\t2\t1\ttrue"]


def test_caught_nested_failure_does_not_leave_placeholder() -> None:
    lines = run_lua(r'''
local attempts = 0
local sources = {
  bad = "local M = ...; cap.bump(); error('first failure')",
  catcher = "local M = ...; M.ok = pcall(function() require('bad') end)",
}
local l = require("loader").new(sources, {bump = function() attempts = attempts + 1 end})
print(l:require("catcher").ok, pcall(function() l:require("bad") end), attempts)
''')
    assert lines == ["false\tfalse\t2"]


def test_escape_attempts_and_all_cache_boundaries() -> None:
    lines = run_lua(r'''
local probe = [[
local M = ...
local names = {'_G', 'package', 'debug', 'io', 'os', 'load', 'loadfile', 'dofile'}
M.absent = true
for _, name in ipairs(names) do if _ENV then M.absent = false end end
return M
]]
local escapes = [[
local M = ...
M.host = (_G or package or debug or io or os or load or loadfile or dofile) ~= nil
M.cap_mutation = pcall(function() cap.token = 'stolen' end)
M.nested_mutation = pcall(function() cap.nested.value = 'stolen' end)
M.math_mutation = pcall(function() math.huge = 1 end)
M.hidden_tools = (math.random ~= nil or math.randomseed ~= nil or string.dump ~= nil)
M.cap_meta = getmetatable(cap)
M.math_meta = getmetatable(math)
M.bad_name = pcall(function() require('../../etc/passwd') end)
M.missing = pcall(function() require('not-present') end)
]]
local sources = {escapes = escapes}
local one = require("loader").new(sources, {token = "one", nested = {value = "safe"}})
local two = require("loader").new(sources, {token = "two", nested = {value = "safe"}})
local a, b = one:require("escapes"), two:require("escapes")
print(a.host, a.cap_mutation, a.nested_mutation, a.math_mutation, a.hidden_tools, a.cap_meta, a.math_meta, a.bad_name, a.missing, a == b)
''')
    assert lines == ["false\tfalse\tfalse\tfalse\tfalse\tread-only\tread-only\tfalse\tfalse\tfalse"]


def test_environment_identifier_and_invalid_contract_inputs_fail() -> None:
    lines = run_lua(r'''
local sources = {
  env = "local M = ...; M.env = _ENV",
  scalar = "return 42",
  syntax = "this is not lua !!!",
}
local l = require("loader").new(sources, {})
local function fails(name) local ok = pcall(function() l:require(name) end); return not ok end
print(fails("env"), fails("scalar"), fails("syntax"), fails("bad/name"), fails(""))
''')
    assert lines == ["true\ttrue\ttrue\ttrue\ttrue"]


def test_source_mutation_and_runtime_path_are_observable() -> None:
    lines = run_lua(r'''
local sources = {value = "local M = ...; M.n = 11"}
local first = require("loader").new(sources, {}):require("value").n
sources.value = "local M = ...; M.n = 12"
local second = require("loader").new(sources, {}):require("value").n
print(first, second, first ~= second)
''')
    assert lines == ["11\t12\ttrue"]

    if LUA is None:
        pytest.skip("Lua 5.4 is not installed")
    scenario = 'return {sources={x="local M = ...; M.answer = cap.value"}, capabilities={value=37}, requests={"x"}}\n'
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "scenario.lua"
        path.write_text(scenario, encoding="utf-8")
        env = {**os.environ, "LUA_PATH": f"{FILES}/?.lua;;"}
        run = subprocess.run([LUA, str(FILES / "loader_runtime.lua"), str(path)], text=True, capture_output=True, env=env, check=True)
    assert run.stdout == 'ok\tx\t{["answer"]=37}\n'


def test_kernel_cannot_bypass_protected_runtime_or_host_require() -> None:
    source = (FILES / "loader.lua").read_text(encoding="utf-8")
    compact = re.sub(r"--[^\n]*", "", source)
    assert re.search(r"require\s*\(\s*[\"']sandbox_runtime[\"']\s*\)", compact)
    compact = re.sub(r"require\s*\(\s*[\"']sandbox_runtime[\"']\s*\)", "", compact, count=1)
    forbidden = ("_G", "package", "debug", "io.", "os.", "load(", "loadfile", "dofile", "setmetatable", "getmetatable")
    assert not any(token in compact for token in forbidden)
    assert ".compile" in source and ".environment" in source
