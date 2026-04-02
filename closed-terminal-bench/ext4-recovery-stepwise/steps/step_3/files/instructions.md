# Step 3: Build Merkle Tree Manifest Tool

The toolchain at `/app/toolchain/` contains a Go program that builds a
Merkle-tree manifest of the workspace. It has bugs — fix them and run it.

## Requirements

1. Fix the bugs in `/app/toolchain/manifest_tool.go`
2. Build: `cd /app/toolchain && go build -o /app/manifest_tool .`
3. Run: `/app/manifest_tool /app/workspace /app/manifest.txt`

## Manifest Format

Line 1: root hash (64 hex chars, SHA-256 of root directory node)

Remaining lines: `<hash>  <relative_path>` for each file
                 `<hash>  <relative_path>/` for each directory

Lines after the root are sorted lexicographically by path.

Directory hash = SHA-256 of concatenated children sorted **by name**:

    name\0hash\n  for each child (sorted by name, not by hash)

## Known Bugs to Fix

There are two bugs in `manifest_tool.go`:

1. **Bug A (wrong sort key)**: `hashDir()` sorts children by their hash value
   instead of by their name. Fix: sort by `children[i].name` instead of
   `children[i].hash`.

2. **Bug B (missing directory entries)**: The output loop skips directory
   entries (`continue` when `e.isDir`). Fix: remove the `continue` so that
   directory entries are included in the output with a trailing `/` on their
   path.

## Verification

    python3 -m pytest /app/step_3/files/tests.py -v

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test or verifier files.
