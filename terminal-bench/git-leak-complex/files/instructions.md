# Git Leak Recovery and Sanitize (Complex)

The repository at `/app/repo_large` contains leaked secrets throughout its history: ~1000 commits over 5 years, multiple branches with merge commits, multiple annotated tags, git notes, and commits with differing author and committer identities.

The secret strings to remove are listed in `/app/files/secret_patterns.txt` (one per line).

Sanitize `/app/repo_large` by removing all occurrences of these secrets from the entire repository history, while preserving its full repository integrity exactly.

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

**Important:** The secrets may have been embedded in unusual locations and formats throughout the repository history — not just in regular source files and commit messages. They may appear in configuration metadata (e.g. `.gitmodules`), encoded forms (e.g. base64), or even split across multiple lines. Scan thoroughly and consider all possible representations.

## Important: Metadata preservation

Your rewrite must preserve committer dates exactly. Tools like `git filter-branch` may update committer dates by default. Prefer `git fast-export`/`git fast-import` which preserves all metadata by default.

**Warning:** The repository has ~1000 commits across multiple branches with merge commits. A naive `git filter-branch` will likely corrupt committer dates or miss branches. Use `git filter-repo` or `git fast-export`/`git fast-import` for correctness.

## Verification

- Tests at `/app/files/tests.py`.

## Self-verification (important!)

Verify your solution against the visible tests:

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest. Running them directly with python silently does nothing.

## Constraints

- Work entirely offline in the container.
- Use standard git tooling only.
- Do not modify verifier files.
- Keep `.git/config` unchanged.
