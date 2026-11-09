package cache;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;

public final class ControlledLoader implements AsyncLoader<String, String> {
    public record Call(String key, long generation, CompletableFuture<String> future) {}

    private final List<Call> calls = new ArrayList<>();

    @Override
    public synchronized CompletableFuture<String> load(String key, long generation) {
        CompletableFuture<String> future = new CompletableFuture<>();
        calls.add(new Call(key, generation, future));
        notifyAll();
        return future;
    }

    public synchronized int count() {
        return calls.size();
    }

    public synchronized Call call(int index) {
        return calls.get(index);
    }
}
