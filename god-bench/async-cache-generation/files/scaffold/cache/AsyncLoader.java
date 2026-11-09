package cache;

import java.util.concurrent.CompletableFuture;

@FunctionalInterface
public interface AsyncLoader<K, V> {
    CompletableFuture<V> load(K key, long generation);
}
