package cache;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class HiddenTests {
    public static void main(String[] args) throws Exception {
        generationsArePerKeyAndLoadsAreShared();
        staleSuccessAndFailureCannotTouchCurrentEntry();
        failureCancellationNullAndThrowRetry();
        callerCancellationIsIsolated();
        deterministicInterleavingsAreLinearizable();
        followersProgressWhileLoaderIsBlocked();
        invalidateProgressesWhileLoaderIsBlocked();
        userCompletionRunsOutsideInternalLock();
        nullKeysAreRejected();
        candidateIsTheCompiledKernel();
        System.out.println("hidden cache tests passed");
    }

    private static void generationsArePerKeyAndLoadsAreShared() {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> a0 = cache.get("a");
        CompletableFuture<String> a0Again = cache.get("a");
        CompletableFuture<String> b0 = cache.get("b");
        Assertions.equal(2, loader.count(), "one load per key and generation");
        Assertions.equal(0L, loader.call(0).generation(), "a initial generation");
        Assertions.equal(0L, loader.call(1).generation(), "b initial generation");
        cache.invalidate("a");
        CompletableFuture<String> a1 = cache.get("a");
        Assertions.equal(1L, loader.call(2).generation(), "a incremented generation");
        loader.call(0).future().complete("a-old");
        loader.call(1).future().complete("b");
        loader.call(2).future().complete("a-new");
        Assertions.equal("a-old", Assertions.join(a0), "old a caller");
        Assertions.equal("a-old", Assertions.join(a0Again), "shared old a caller");
        Assertions.equal("b", Assertions.join(b0), "independent b caller");
        Assertions.equal("a-new", Assertions.join(a1), "new a caller");
    }

    private static void staleSuccessAndFailureCannotTouchCurrentEntry() {
        for (boolean oldSucceeds : new boolean[] {true, false}) {
            ControlledLoader loader = new ControlledLoader();
            VersionedCache<String, String> cache = new VersionedCache<>(loader);
            CompletableFuture<String> old = cache.get("k");
            cache.invalidate("k");
            CompletableFuture<String> fresh = cache.get("k");
            loader.call(1).future().complete("fresh");
            Assertions.equal("fresh", Assertions.join(fresh), "fresh completion");
            if (oldSucceeds) {
                loader.call(0).future().complete("stale");
                Assertions.equal("stale", Assertions.join(old), "old success caller");
            } else {
                loader.call(0).future().completeExceptionally(new IOException("old"));
                expectFailure(old, "old failure caller");
            }
            Assertions.equal("fresh", Assertions.join(cache.get("k")), "old completion altered cache");
            Assertions.equal(2, loader.count(), "old completion evicted fresh entry");
        }
    }

    private static void failureCancellationNullAndThrowRetry() {
        AtomicInteger attempts = new AtomicInteger();
        AsyncLoader<String, String> adversarial = (key, generation) -> {
            int attempt = attempts.getAndIncrement();
            return switch (attempt) {
                case 0 -> CompletableFuture.failedFuture(new IOException("failure"));
                case 1 -> {
                    CompletableFuture<String> cancelled = new CompletableFuture<>();
                    cancelled.cancel(false);
                    yield cancelled;
                }
                case 2 -> null;
                case 3 -> throw new IllegalStateException("synchronous");
                case 4 -> CompletableFuture.completedFuture(null);
                default -> CompletableFuture.completedFuture("recovered");
            };
        };
        VersionedCache<String, String> cache = new VersionedCache<>(adversarial);
        for (int attempt = 0; attempt < 5; attempt++) {
            CompletableFuture<String> result;
            try {
                result = cache.get("x");
            } catch (Throwable thrown) {
                throw new AssertionError("get must represent loader faults in its future", thrown);
            }
            expectFailure(result, "adversarial attempt " + attempt);
        }
        Assertions.equal("recovered", Assertions.join(cache.get("x")), "retry after all failure modes");
        Assertions.equal(6, attempts.get(), "each failed exact entry must be evicted");
    }

    private static void callerCancellationIsIsolated() {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> cancelled = cache.get("x");
        CompletableFuture<String> observer = cache.get("x");
        Assertions.check(cancelled != observer, "callers need cancellation-isolated views");
        Assertions.check(cancelled.cancel(true), "caller future should be cancellable");
        Assertions.check(!loader.call(0).future().isCancelled(), "caller cancelled loader future");
        loader.call(0).future().complete("value");
        Assertions.equal("value", Assertions.join(observer), "other caller was poisoned");
        Assertions.equal("value", Assertions.join(cache.get("x")), "cancelled view evicted cache");
        Assertions.equal(1, loader.count(), "caller cancellation caused reload");
    }

    private static void deterministicInterleavingsAreLinearizable() {
        List<List<Character>> orders = permutations(List.of('C', 'I', 'G'));
        for (List<Character> order : orders) {
            ControlledLoader loader = new ControlledLoader();
            VersionedCache<String, String> cache = new VersionedCache<>(loader);
            CompletableFuture<String> old = cache.get("key");
            CompletableFuture<String> observed = null;
            for (char operation : order) {
                if (operation == 'C') {
                    loader.call(0).future().complete("old");
                } else if (operation == 'I') {
                    cache.invalidate("key");
                } else {
                    observed = cache.get("key");
                }
            }
            Assertions.equal("old", Assertions.join(old), "old history result " + order);
            CompletableFuture<String> current = cache.get("key");
            Assertions.equal(2, loader.count(), "history has exactly generations zero and one " + order);
            Assertions.equal(1L, loader.call(1).generation(), "history generation " + order);
            loader.call(1).future().complete("new");
            Assertions.equal("new", Assertions.join(current), "linearized current value " + order);
            if (order.indexOf('G') > order.indexOf('I')) {
                Assertions.equal("new", Assertions.join(observed), "post-invalidate get " + order);
            } else {
                Assertions.equal("old", Assertions.join(observed), "pre-invalidate get " + order);
            }
            Assertions.equal("new", Assertions.join(cache.get("key")), "stable history result " + order);
        }
    }

    private static void invalidateProgressesWhileLoaderIsBlocked() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CompletableFuture<String> oldLoad = new CompletableFuture<>();
        AtomicInteger calls = new AtomicInteger();
        AsyncLoader<String, String> loader = (key, generation) -> {
            if (calls.getAndIncrement() == 0) {
                entered.countDown();
                await(release, "release blocked loader");
                return oldLoad;
            }
            return CompletableFuture.completedFuture("new");
        };
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        AtomicReference<CompletableFuture<String>> oldCaller = new AtomicReference<>();
        Thread getter = new Thread(() -> oldCaller.set(cache.get("k")), "blocked-get");
        getter.start();
        Assertions.check(entered.await(2, TimeUnit.SECONDS), "loader did not start");
        CountDownLatch invalidated = new CountDownLatch(1);
        Thread invalidator = new Thread(() -> {
            cache.invalidate("k");
            invalidated.countDown();
        }, "invalidator");
        invalidator.start();
        Assertions.check(invalidated.await(2, TimeUnit.SECONDS), "loader ran under generation lock");
        release.countDown();
        getter.join(2000);
        invalidator.join(2000);
        oldLoad.complete("old");
        Assertions.equal("old", Assertions.join(oldCaller.get()), "blocked old caller");
        Assertions.equal("new", Assertions.join(cache.get("k")), "post-overlap generation");
        Assertions.equal(2, calls.get(), "overlap load count");
    }

    private static void followersProgressWhileLoaderIsBlocked() throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CompletableFuture<String> load = new CompletableFuture<>();
        AtomicInteger calls = new AtomicInteger();
        VersionedCache<String, String> cache = new VersionedCache<>((key, generation) -> {
            calls.incrementAndGet();
            entered.countDown();
            await(release, "release shared loader");
            return load;
        });
        AtomicReference<CompletableFuture<String>> first = new AtomicReference<>();
        AtomicReference<CompletableFuture<String>> follower = new AtomicReference<>();
        CountDownLatch followerReturned = new CountDownLatch(1);
        Thread owner = new Thread(() -> first.set(cache.get("shared")), "load-owner");
        owner.start();
        Assertions.check(entered.await(2, TimeUnit.SECONDS), "shared loader did not start");
        Thread second = new Thread(() -> {
            follower.set(cache.get("shared"));
            followerReturned.countDown();
        }, "load-follower");
        second.start();
        Assertions.check(followerReturned.await(2, TimeUnit.SECONDS), "follower blocked behind user loader");
        Assertions.equal(1, calls.get(), "concurrent follower started another load");
        release.countDown();
        owner.join(2000);
        second.join(2000);
        load.complete("shared-value");
        Assertions.equal("shared-value", Assertions.join(first.get()), "owner shared value");
        Assertions.equal("shared-value", Assertions.join(follower.get()), "follower shared value");
    }

    private static void userCompletionRunsOutsideInternalLock() throws Exception {
        ControlledLoader loader = new ControlledLoader();
        VersionedCache<String, String> cache = new VersionedCache<>(loader);
        CompletableFuture<String> caller = cache.get("k");
        CountDownLatch callbackDone = new CountDownLatch(1);
        caller.thenRun(() -> {
            Thread invalidator = new Thread(() -> cache.invalidate("k"), "callback-invalidator");
            invalidator.start();
            try {
                invalidator.join(1500);
            } catch (InterruptedException interrupted) {
                throw new CompletionException(interrupted);
            }
            Assertions.check(!invalidator.isAlive(), "user completion callback observed internal lock");
            callbackDone.countDown();
        });
        loader.call(0).future().complete("done");
        Assertions.check(callbackDone.await(2, TimeUnit.SECONDS), "completion callback did not finish");
    }

    private static void nullKeysAreRejected() {
        VersionedCache<String, String> cache = new VersionedCache<>(
            (key, generation) -> CompletableFuture.completedFuture("x")
        );
        expectNullPointer(() -> cache.get(null), "get null key");
        expectNullPointer(() -> cache.invalidate(null), "invalidate null key");
    }

    private static void candidateIsTheCompiledKernel() throws IOException {
        Path candidate = Path.of("/app/files/src/main/java/VersionedCache.java");
        Assertions.check(Files.isRegularFile(candidate) && !Files.isSymbolicLink(candidate), "candidate artifact type");
        String submitted = Files.readString(candidate);
        String declaration = "public final class " + "VersionedCache";
        Assertions.check(submitted.contains(declaration), "candidate class missing");
        long declarations;
        try (var files = Files.list(Path.of("/tmp/async-cache-generation-build/src/cache"))) {
            declarations = files.filter(path -> path.toString().endsWith(".java"))
                .map(HiddenTests::readUnchecked)
                .filter(text -> text.contains(declaration))
                .count();
        }
        Assertions.equal(1L, declarations, "trusted bypass implementation present");
    }

    private static String readUnchecked(Path path) {
        try {
            return Files.readString(path);
        } catch (IOException error) {
            throw new CompletionException(error);
        }
    }

    private static void expectFailure(CompletableFuture<?> future, String message) {
        try {
            Assertions.join(future);
            throw new AssertionError(message + ": unexpectedly successful");
        } catch (CompletionException | java.util.concurrent.CancellationException expected) {
            // Expected.
        }
    }

    private static void expectNullPointer(Runnable action, String message) {
        try {
            action.run();
            throw new AssertionError(message + ": no NullPointerException");
        } catch (NullPointerException expected) {
            // Expected.
        }
    }

    private static void await(CountDownLatch latch, String message) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new AssertionError(message);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new CompletionException(interrupted);
        }
    }

    private static <T> List<List<T>> permutations(List<T> values) {
        List<List<T>> result = new ArrayList<>();
        permute(new ArrayList<>(values), 0, result);
        return result;
    }

    private static <T> void permute(List<T> values, int index, List<List<T>> result) {
        if (index == values.size()) {
            result.add(List.copyOf(values));
            return;
        }
        for (int next = index; next < values.size(); next++) {
            T value = values.get(index);
            values.set(index, values.get(next));
            values.set(next, value);
            permute(values, index + 1, result);
            value = values.get(index);
            values.set(index, values.get(next));
            values.set(next, value);
        }
    }
}
