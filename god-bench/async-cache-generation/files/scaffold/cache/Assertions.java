package cache;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

public final class Assertions {
    private Assertions() {}

    public static void equal(Object expected, Object actual, String message) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(message + ": expected=" + expected + " actual=" + actual);
        }
    }

    public static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static <T> T join(CompletableFuture<T> future) {
        return future.orTimeout(Duration.ofSeconds(2).toMillis(), java.util.concurrent.TimeUnit.MILLISECONDS).join();
    }

    public static void fails(CompletableFuture<?> future, String message) {
        try {
            join(future);
            throw new AssertionError(message + ": completed successfully");
        } catch (CompletionException expected) {
            // Expected exceptional or loader-cancelled completion.
        }
    }
}
