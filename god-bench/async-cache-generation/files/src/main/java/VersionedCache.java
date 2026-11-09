package cache;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicLong;

/** Starter implementation. It incorrectly republishes stale loads and exposes them directly. */
public final class VersionedCache<K, V> {
    private final AsyncLoader<K, V> loader;
    private final ConcurrentHashMap<K, AtomicLong> generations = new ConcurrentHashMap<>();
    private final ConcurrentHashMap<K, CompletableFuture<V>> entries = new ConcurrentHashMap<>();

    public VersionedCache(AsyncLoader<K, V> loader) {
        this.loader = Objects.requireNonNull(loader, "loader");
    }

    public CompletableFuture<V> get(K key) {
        Objects.requireNonNull(key, "key");
        long generation = generations.computeIfAbsent(key, ignored -> new AtomicLong()).get();
        return entries.computeIfAbsent(key, ignored -> {
            CompletableFuture<V> loaded = loader.load(key, generation);
            loaded.thenAccept(value -> entries.put(key, loaded));
            return loaded;
        });
    }

    public void invalidate(K key) {
        Objects.requireNonNull(key, "key");
        generations.computeIfAbsent(key, ignored -> new AtomicLong()).incrementAndGet();
        entries.remove(key);
    }
}
