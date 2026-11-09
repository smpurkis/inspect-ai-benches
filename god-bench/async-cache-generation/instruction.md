# Async Cache Generation Race

Edit only `src/main/java/VersionedCache.java`. Preserve the public generic class and its constructor, `get`, and `invalidate` signatures.

One loader invocation must be shared per key and generation. `invalidate(key)` is a linearization boundary: every later `get(key)` starts or shares the next generation, and an older completion must never become the cached value. Failed or loader-cancelled entries are evicted for retry. Cancelling a caller's returned future must not cancel or poison the shared load or another caller. Different keys progress independently, loader callbacks may complete synchronously, and user loader code must not execute while an internal generation lock is held. Null keys, loader futures, and values follow `/app/files/TASK.md`.

Run `/app/files/run_tests.sh public`. Network access and dependencies beyond the JDK are forbidden.
