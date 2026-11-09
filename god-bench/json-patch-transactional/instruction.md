# Transactional JSON Patch

Edit only `src/applyOperation.ts`. Repair RFC 6902 `move` and `copy` according to `TASK.md` and `contract.toml`; the supplied pointer parser, CLI, types, and build configuration are trusted scaffold.

Build with `make -C /app/files clean all` and run `python3 -m pytest -q /app/files/tests.py`. Network access and new dependencies are forbidden.
