# VersionedCache Contract

Only `src/main/java/VersionedCache.java` is editable. Keep `package cache;` and this API:

```java
public final class VersionedCache<K, V> {
    public VersionedCache(AsyncLoader<K, V> loader);
    public CompletableFuture<V> get(K key);
    public void invalidate(K key);
}
```

`AsyncLoader.load(K key, long generation)` is supplied. Generation zero is the first generation of a key; each completed `invalidate(key)` increments exactly that key's generation once.

Semantics:

1. Concurrent and sequential cache misses for one key/generation invoke the loader exactly once and share its eventual result. A successful result remains cached in that generation.
2. `invalidate` and the selection/publication portion of `get` are linearizable per key. A `get` invoked after `invalidate` returns must not observe or join an older generation. An old load may still complete its existing callers, but must never publish into or remove a newer generation.
3. Loader exceptional completion, cancellation, a synchronous throw from `load`, a null loader future, or a null loaded value completes current callers exceptionally and evicts that exact entry so the next `get` retries in the same generation.
4. Every `get` returns a cancellation-isolated view. Cancelling it does not cancel the shared loader future, the shared cache result, or another caller. It does not evict a healthy entry.
5. Null keys are rejected with `NullPointerException`. `invalidate` does not cancel old loads. Keys are independent.
6. User code, including `loader.load` and completion callbacks, must execute outside internal locks. Reentrant `get`/`invalidate` from loader code must not deadlock.

No timing sleeps are needed to solve or test the task. The trusted harness uses manually controlled futures, barriers, and bounded joins.
