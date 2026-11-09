#!/usr/bin/env lua
-- Protected deterministic adapter. Scenario files are trusted input data/code.
local scenario_path = assert(arg[1], "usage: loader_runtime.lua SCENARIO.lua")
local scenario = assert(loadfile(scenario_path, "t", {}))()
local loader = require("loader").new(assert(scenario.sources), scenario.capabilities or {})

local function encode(value, active)
  local kind = type(value)
  if kind == "nil" then return "nil" end
  if kind == "boolean" or kind == "number" then return tostring(value) end
  if kind == "string" then return string.format("%q", value) end
  if kind ~= "table" then error("cannot encode " .. kind) end
  active = active or {}
  if active[value] then return '"<cycle>"' end
  active[value] = true
  local keys = {}
  for key in pairs(value) do keys[#keys + 1] = key end
  table.sort(keys, function(a, b) return tostring(a) < tostring(b) end)
  local fields = {}
  for _, key in ipairs(keys) do
    fields[#fields + 1] = "[" .. encode(key, active) .. "]=" .. encode(value[key], active)
  end
  active[value] = nil
  return "{" .. table.concat(fields, ",") .. "}"
end

for _, name in ipairs(scenario.requests or {}) do
  local ok, result = pcall(function() return loader:require(name) end)
  if ok then
    print("ok\t" .. name .. "\t" .. encode(result))
  else
    print("error\t" .. name .. "\t" .. tostring(result):gsub("[\r\n].*", ""))
  end
end
