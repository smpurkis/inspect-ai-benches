# Git Leak Recovery and Sanitize - Step 2

Precondition: complete this only after Step 1 passes.

In `/app/repo`, rewrite history to remove leaked secret material from all reachable history.

## Requirements

- Identify the leaked secret by inspecting the git history (e.g. `git log --all -p` or `git log --all --oneline`). The secret is already visible in the repository's history — read it from there, or from `/app/repo/.git/hooks/secret-patterns` which you populated in Step 1.
- Replace each occurrence of the secret in tracked file contents with the fingerprinted placeholder described below. Do not delete files or lines — file structure must remain intact.
- Replace the secret in commit messages across history.
- Replace the secret in tag references/annotations across history.
- **MUST: Replacement format.** Every secret occurrence MUST be replaced with `REDACTED-<hex8>` where `<hex8>` is the first 8 hex characters of the SHA-256 hash of that secret's exact string value. Compute it as: `printf '%s' '<secret_value>' | sha256sum | head -c 8`. This applies uniformly to file contents, commit messages, tag annotations, and git notes. Generic placeholders like `<REDACTED>`, `***`, or bare `REDACTED` are NOT acceptable — the tests verify the exact fingerprinted format.
- After rewriting history, purge all unreachable/dangling objects left behind by the rewrite: `git reflog expire --expire=now --all && git gc --prune=now`. This is required — loose dangling objects are checked by the tests even though they are no longer reachable from any branch or tag.
- Remove ALL secrets listed in `/app/repo/.git/hooks/secret-patterns` — there may be more than one.
- Rewrite git notes containing secrets — replace secret content, do not delete the notes. `git notes list` shows note blobs and their target commits.
- Remove the secret from any file whose **filename** contains a secret pattern — the file must not appear under that name in any tree object in history.
- Preserve all commit metadata: author/committer names, emails, and timestamps must be unchanged after the rewrite. The repository has commits from multiple authors (Alice Developer, Bob Smith) and committers (including Agent) — these assignments must survive exactly.
- Preserve all commit messages — only the secret portions should change, not the surrounding text. For example, a message like "Commit 5: routine update" must remain identical.
- Preserve the annotated tag v1.0 — it must remain annotated (not lightweight) after the rewrite.

## Verification

- Tests at `/app/step_2/files/tests.py`.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_2/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Scoring

- Step 1 fail → 0
- Step 1 pass, Step 2 fail → 1/3
- Step 1+2 pass, Step 3 fail → 2/3
- All pass → 1.0

## Constraints

- Work entirely offline in the container.
- Use standard git tooling only.
- Do not modify verifier files.
- Keep `.git/config` unchanged.
- You may provide `/app/solve.sh` for reproducibility.
