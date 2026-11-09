# Mutation adequacy map

The hidden harness is intentionally structured to kill these authoring mutations:

- return the loader future directly: `callerCancellationIsIsolated`;
- key entries without a generation: `generationsArePerKeyAndLoadsAreShared`;
- publish or remove without checking entry identity: `staleSuccessAndFailureCannotTouchCurrentEntry`;
- retain exceptional/cancelled/null entries: `failureCancellationNullAndThrowRetry`;
- call user loader while holding the per-key lock: `invalidateProgressesWhileLoaderIsBlocked`;
- hold cache-map computation while loading: `followersProgressWhileLoaderIsBlocked`;
- complete caller views while holding the per-key lock: `userCompletionRunsOutsideInternalLock`;
- reverse invalidate/get ordering or bypass the candidate: deterministic history and source-reachability checks.
