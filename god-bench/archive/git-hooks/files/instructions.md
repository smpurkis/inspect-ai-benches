# Git Secret Remediation

The repository at `/app/repo` contains leaked credentials buried throughout its history and metadata.

The secret patterns are in `/app/repo/secret-patterns.txt` (one per line, fixed-string match).

Remove every trace of these secrets from the repository. After remediation, no git command -- including history search, metadata inspection, object enumeration, or reflog traversal -- should be able to recover any secret. Secrets may be encoded, obfuscated, or hidden in non-obvious locations.

Preserve the repository's branch names, tag names, and commit count. Legitimate content that merely resembles a secret pattern (e.g., documentation examples) must not be removed.

## Verification

Tests at `/app/files/tests.py`.

    python3 -m pytest /app/files/tests.py -v

Do NOT use `python3 tests.py` -- test files require pytest.

## Constraints

- Work entirely offline in the container.
- Do not modify test files.
