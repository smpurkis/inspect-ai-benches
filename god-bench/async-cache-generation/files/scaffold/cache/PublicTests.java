package cache;

import java.util.concurrent.CompletableFuture;

public final class PublicTests {
    public static void main(String[] args) {
        if (args.length == 1) {
            switch (args[0]) {
                case "normal" -> normalSharedLoad();
                case "edge" -> edgeStaleCompletion();
                case "invariant" -> invariantFailureRetries();
                case "deterministic" -> deterministicReplay();
                default -> throw new IllegalArgumentException("unknown public test");
            }
            return;
        }
        normalSharedLoad();
        edgeStaleCompletion();
        invariantFailureRetries();
        deterministicReplay();
        System.out.println("public cache tests passed");
    }

    private static void normalSharedLoad() {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> first = cache.get("a");
        CompletableFuture<String> second = cache.get("a");
        Assertions.equal(1, loader.count(), "same generation must share one load");
        loader.call(0).future().complete("value");
        Assertions.equal("value", Assertions.join(first), "first caller result");
        Assertions.equal("value", Assertions.join(second), "second caller result");
        Assertions.equal("value", Assertions.join(cache.get("a")), "cached result");
        Assertions.equal(1, loader.count(), "cache hit must not reload");
    }

    private static void edgeStaleCompletion() {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> old = cache.get("key");
        cache.invalidate("key");
        CompletableFuture<String> current = cache.get("key");
        Assertions.equal(1L, loader.call(1).generation(), "generation after invalidation");
        loader.call(0).future().complete("stale");
        loader.call(1).future().complete("fresh");
        Assertions.equal("stale", Assertions.join(old), "old caller may finish");
        Assertions.equal("fresh", Assertions.join(current), "new caller result");
        Assertions.equal("fresh", Assertions.join(cache.get("key")), "stale load republished");
    }

    private static void invariantFailureRetries() {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> failed = cache.get("x");
        loader.call(0).future().completeExceptionally(new IllegalStateException("boom"));
        Assertions.fails(failed, "failed load");
        CompletableFuture<String> retry = cache.get("x");
        Assertions.equal(2, loader.count(), "failure must evict exact entry");
        loader.call(1).future().complete("ok");
        Assertions.equal("ok", Assertions.join(retry), "retry value");
    }

    private static void deterministicReplay() {
        for (int iteration = 0; iteration < 3; iteration++) {
            ControlledLoader loader = new ControlledLoader();
            VersionedCache<String, String> cache = new VersionedCache<>(loader);
            CompletableFuture<String> abandoned = cache.get("z");
            abandoned.cancel(false);
            CompletableFuture<String> observer = cache.get("z");
            loader.call(0).future().complete("stable");
            Assertions.equal("stable", Assertions.join(observer), "caller cancellation leaked");
            Assertions.check(!loader.call(0).future().isCancelled(), "shared load was cancelled");
        }
    }
}
