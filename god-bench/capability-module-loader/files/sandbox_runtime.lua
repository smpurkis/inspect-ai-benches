-- Trusted compiler and read-only membranes. The candidate loader cannot edit this file.
local native_load = load
local native_type = type
local native_getmetatable = getmetatable
local native_next = next
local native_rawget = rawget
local native_rawlen = rawlen

local runtime = {}

local function readonly(value, seen)
  if native_type(value) ~= "table" then
    return value
  end
  seen = seen or {}
  if seen[value] then
    return seen[value]
  end
  local proxy = {}
  seen[value] = proxy
  local mt = {
    __index = function(_, key) return readonly(native_rawget(value, key), seen) end,
    __newindex = function() error("attempt to modify a read-only table", 2) end,
    __len = function() return native_rawlen(value) end,
    __pairs = function()
      local key
      return function()
        key = native_next(value, key)
        if key ~= nil then return readonly(key, seen), readonly(native_rawget(value, key), seen) end
      end
    end,
    __metatable = "read-only",
  }
  return setmetatable(proxy, mt)
end

function runtime.readonly(value)
  return readonly(value, {})
end

local function library_without(value, excluded)
  local copy = {}
  for key, item in native_next, value do
    if not excluded[key] then copy[key] = item end
  end
  return readonly(copy, {})
end

local safe_math = library_without(math, {random = true, randomseed = true})
local safe_string = library_without(string, {dump = true})

local safe_base = {
  assert = assert,
  error = error,
  getmetatable = function(value)
    local mt = native_getmetatable(value)
    if native_type(mt) == "table" then return "protected" end
    return mt
  end,
  ipairs = ipairs,
  next = next,
  pairs = pairs,
  pcall = pcall,
  rawequal = rawequal,
  select = select,
  tonumber = tonumber,
  tostring = tostring,
  type = type,
  xpcall = xpcall,
  math = safe_math,
  string = safe_string,
  table = readonly(table, {}),
  utf8 = readonly(utf8, {}),
}

function runtime.environment(capabilities, importer)
  local environment = {cap = readonly(capabilities, {}), require = importer}
  return setmetatable(environment, {
    __index = safe_base,
    __newindex = function(_, key) error("sandbox global write: " .. tostring(key), 2) end,
    __metatable = "sandbox",
  })
end

function runtime.compile(source, name, environment)
  if native_type(source) ~= "string" then
    return nil, "module source is not a string"
  end
  if source:find("%f[%a_]_ENV%f[^%w_]") then
    return nil, "direct _ENV access is forbidden"
  end
  return native_load(source, "@module:" .. name, "t", environment)
end

return runtime
