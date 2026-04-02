# Git Leak Recovery and Sanitize - Step 1

Install commit-time guard hooks in `/app/repo/.git/hooks` that enforce secret blocking before commits are created.

## Requirements

- Read fixed-string patterns from `/app/repo/.git/hooks/secret-patterns` (one pattern per line). Ignore empty or whitespace-only lines — an empty pattern passed to `grep` matches every line, which would block all commits.
- Treat every non-empty line as an independent fixed-string rule. Patterns must be matched as fixed strings even when they contain shell metacharacters (`$`, `*`, `[`, `\`). Use `grep -F` and avoid interpolating pattern values into unquoted shell variables.
- Scan staged file content for each pattern before the commit is created. **Critical:** scan the actual staged (index) version of each file, not the working-tree copy. Use `git show :path` to read each staged file's content — this works for both text and binary files. Do not rely on `git diff --cached` output, which suppresses binary file content.
- Detect patterns even when they span adjacent line boundaries in a staged file. A line-by-line grep will miss a pattern whose first half ends one line and second half begins the next. **You must strip newlines from the staged content before searching** — e.g. `content=$(git show ":$file" | tr -d '\n')` — then run `grep -F` against the collapsed single-line string. Do not grep the raw multi-line output directly.
- Scan the proposed commit message for each pattern before the commit is created.
- The hooks must also fire on `git commit --amend`. Both the new commit message and the staged index must be scanned, exactly as for a normal commit.
- Abort commit with a descriptive non-zero exit status if any pattern matches. **Important:** ensure the non-zero exit propagates correctly to the hook's top-level shell — `exit 1` inside a pipeline subshell (e.g. `cmd | while read ...; do exit 1; done`) does **not** propagate. Use a temporary file, a variable, or restructure the logic to avoid this trap.
- Allow commits with no matching patterns to proceed normally.
- On rejection, leave `HEAD`, the index, and the working tree unchanged.

## Verification

- Tests at `/app/step_1/files/tests.py`.

## Self-verification (important!)

Before completing this step, verify your solution against the visible tests:

    python3 -m pytest /app/step_1/files/tests.py -v

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
