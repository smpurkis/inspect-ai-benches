-- Candidate kernel. This implementation is intentionally unsafe and incomplete.
local runtime = require("sandbox_runtime")

local loader = {}

function loader.new(sources, capabilities)
  local cache = package.loaded
  local instance = {}

  function instance:require(name)
    if cache[name] ~= nil then
      return cache[name]
    end
    local source = sources[name]
    if source == nil then
      error("module not found: " .. tostring(name))
    end
    local exports = {}
    cache[name] = exports
    local environment = setmetatable({cap = capabilities}, {__index = _G})
    environment.require = function(dependency) return self:require(dependency) end
    local chunk, compile_error = load(source, "@" .. name, "t", environment)
    if not chunk then error(compile_error) end
    local result = chunk(exports)
    if result ~= nil then cache[name] = result end
    return cache[name]
  end

  return instance
end

return loader
