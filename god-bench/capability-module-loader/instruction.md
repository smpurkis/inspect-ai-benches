# Capability-Safe Lua Module Loader

Edit only `loader.lua`. Implement `loader.new(sources, capabilities)`, returning an object whose `:require(name)` method loads string-valued modules from `sources`.

Each module receives its stable export table as `...`, a sandboxed `require`, and a read-only `cap` membrane. A module must return a table or `nil`; returned fields are copied into the stable export table. Load each module at most once, preserve table identity through cycles, and make cycle results independent of the root first requested. Missing modules and invalid returns are errors. A failed outer load must remove every cache entry created by that load so a retry starts cleanly; already successful entries from earlier calls remain cached.

Use only `sandbox_runtime.lua` to compile modules and construct environments. Sandboxed code must not reach host globals, mutable standard-library tables, metatables, debug facilities, `io`, `os`, the filesystem, native `require`, `package.loaded`, source maps, or another loader's capabilities/cache. Do not use `_G`, `package`, `debug`, `io`, `os`, `load`, `loadfile`, `dofile`, or native `require` in the kernel. Module names must match `^[A-Za-z][A-Za-z0-9_.-]*$`.

The protected runtime harness accepts a trusted Lua scenario file and prints deterministic results. Work offline, add no dependencies, and do not modify any file except `loader.lua`.

Run `python3 -m pytest -q /app/files/tests.py`.
