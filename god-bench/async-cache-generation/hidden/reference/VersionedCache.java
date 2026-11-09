package cache;

import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.function.Function;

public final class VersionedCache<K, V> {
    private static final class Entry<V> {
        final long generation;
        final CompletableFuture<V> shared = new CompletableFuture<>();

        Entry(long generation) {
            this.generation = generation;
        }
    }

    private static final class Cell<V> {
        long generation;
        Entry<V> entry;
    }

    private final AsyncLoader<K, V> loader;
    private final ConcurrentHashMap<K, Cell<V>> cells = new ConcurrentHashMap<>();

    public VersionedCache(AsyncLoader<K, V> loader) {
        this.loader = Objects.requireNonNull(loader, "loader");
    }

    public CompletableFuture<V> get(K key) {
        Objects.requireNonNull(key, "key");
        Cell<V> cell = cells.computeIfAbsent(key, ignored -> new Cell<>());
        Entry<V> selected;
        boolean start = false;
        synchronized (cell) {
            selected = cell.entry;
            if (selected == null || selected.generation != cell.generation) {
                selected = new Entry<>(cell.generation);
                cell.entry = selected;
                start = true;
            }
        }
        if (start) {
            startLoad(key, cell, selected);
        }
        return selected.shared.thenApply(Function.identity());
    }

    public void invalidate(K key) {
        Objects.requireNonNull(key, "key");
        Cell<V> cell = cells.computeIfAbsent(key, ignored -> new Cell<>());
        synchronized (cell) {
            cell.generation++;
            cell.entry = null;
        }
    }

    private void startLoad(K key, Cell<V> cell, Entry<V> entry) {
        CompletableFuture<V> loaded;
        try {
            loaded = Objects.requireNonNull(
                loader.load(key, entry.generation), "loader returned null future"
            );
        } catch (Throwable failure) {
            fail(cell, entry, failure);
            return;
        }
        loaded.whenComplete((value, failure) -> {
            if (failure != null) {
                fail(cell, entry, failure);
            } else if (value == null) {
                fail(cell, entry, new NullPointerException("loader returned null value"));
            } else {
                entry.shared.complete(value);
            }
        });
    }

    private void fail(Cell<V> cell, Entry<V> entry, Throwable failure) {
        synchronized (cell) {
            if (cell.entry == entry) {
                cell.entry = null;
            }
        }
        entry.shared.completeExceptionally(failure);
    }
}
