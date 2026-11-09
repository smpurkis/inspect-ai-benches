# Raft Snapshot Reconciliation

Edit only `raft/reconcile.go`. Implement `Reconcile` without changing its signature or the trusted types.

Treat `State.Snapshot` as the compacted prefix endpoint; `Entries` must remain contiguous from `Snapshot.Index+1`. Reject stale leader terms without changing state or current term. Observe a newer request term even when its log does not match. Match `PrevIndex` against the snapshot when equal, against retained entries when greater, and reject indexes below the snapshot or beyond the retained log. Request entries must be contiguous from `PrevIndex+1`.

Matching retries are idempotent. At the first entry whose term or data differs, truncate that entry and its suffix and append the leader suffix, unless this would alter an index at or below `Commit`, in which case reject the complete request without changing the log or commit. Never truncate an unmatched local suffix merely because a retry contains fewer entries. On acceptance, advance (never lower) commit to `min(LeaderCommit, lastIndex)`. Returned slices must not alias input slices. `MatchIndex` is the last index known to match for accepted requests and zero for rejected requests.

No network or new dependencies are allowed. Build with `GOTOOLCHAIN=local GOPROXY=off go test ./...` from `/app/files`. Run `python3 -m pytest -q /app/files/tests.py`.
