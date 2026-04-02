# Git Leak Recovery and Sanitize - Step 3

Precondition: complete this only after Step 2 passes.

A second, much larger repository has been placed at `/app/repo_large`. It contains the same leaked secrets as `/app/repo` but has a significantly more complex history: ~1000 commits over 5 years, multiple branches with merge commits, multiple annotated tags, git notes, and commits with differing author and committer identities.

Apply the same secret sanitization you performed on `/app/repo` to `/app/repo_large`, and preserve its full repository integrity exactly.

## Requirements

- Preserve commit structure/topology and branch head layout (same commit count, parent relationships, and branch heads; no squashing/reordering).
- Preserve non-secret file contents across commit snapshots.
- Preserve non-secret commit messages and commit metadata (author/committer names, emails, and dates).
- Preserve tag names, targets, and annotated tag messages after secret removal.
- When sanitizing secret-bearing file contents, commit messages, or tag annotations, you may either delete the secret text or replace it with a neutral placeholder such as `[REDACTED]` or `<SECRET>`, but do not change unrelated wording or structure.
- Preserve git notes (attached to commits via `refs/notes/commits`) — their content must be preserved after secret removal.
- Preserve merge commit topology exactly — merge commits have two parents and this must be maintained.
- Preserve committer identity exactly — some commits have different author and committer identities; both must be preserved.
- One valid way to do this is a history rewrite with standard git tooling such as `git fast-export`/`git fast-import`, or an equivalent scripted replay that preserves topology, metadata, and tags; other standard-git approaches are also acceptable if they satisfy the requirements above.

## Important: Metadata preservation

Your rewrite must preserve committer dates exactly. Tools like `git filter-branch` may update committer dates by default. Prefer `git fast-export`/`git fast-import` which preserves all metadata by default.

**Warning:** The repository has ~1000 commits across multiple branches with merge commits. A naive `git filter-branch` will likely corrupt committer dates or miss branches. Use `git filter-repo` or `git fast-export`/`git fast-import` for correctness.

## Verification

- Tests at `/app/step_3/files/tests.py`.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_3/files/tests.py -v

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
