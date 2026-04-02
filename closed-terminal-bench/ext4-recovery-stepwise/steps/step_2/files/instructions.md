# Step 2: Recover and Rebuild the Go Extractor

The repaired disk image contains a Go project under `project/src/` that
extracts a compressed payload into a workspace directory.

## Requirements

1. Extract the Go source code from the repaired disk image.
   Use `debugfs -R "dump <image_path> <local_path>" /app/disk.img` to
   extract files.
2. The source has bugs — fix them so it compiles and runs correctly.
3. Build the extractor binary at `/app/extractor`.
4. Extract the payload (`project/data/payload.tar.gz` in the image) and
   run the extractor to produce the workspace at `/app/workspace/`.

## Key files in the image

- `project/src/extractor.go` — main extractor source (has bugs)
- `project/src/go.mod` — Go module definition
- `project/data/payload.tar.gz` — compressed workspace payload

## Known bugs to fix

There are five bugs in total:

1. **Syntax bug**: a missing closing `}` for the `for` loop body.
2. **Path stripping bug**: `cleanName = cleanName[1:]` strips the first
   character of every entry name, corrupting extracted paths.
3. **File open bug**: `os.O_APPEND` instead of `os.O_TRUNC` causes
   re-runs to append rather than overwrite file contents.
4. **Truncation bug**: files wrapped with `io.LimitReader(r, 4*1024*1024-1)`
   are truncated by 1 byte when they are exactly 4 MB in size (off-by-one
   error). Fix by using the correct size limit or removing the limit.
5. **Non-determinism bug**: file contents are accumulated in a
   `map[string][]byte` before writing. Map iteration order in Go is
   non-deterministic, so output ordering and behaviour may vary between
   runs. Fix by using a slice (ordered) or sorting the keys before writing.

Note: the extractor may produce non-deterministic output across runs until
bug 5 is fixed. Both the truncation issue (bug 4) and the ordering issue
(bug 5) must be corrected for full marks.

## Expected output

After running the fixed extractor:

    /app/extractor <payload_file> /app/workspace

The `/app/workspace/` directory should contain the extracted workspace
with the correct file structure and content, including `data/large_corpus.dat`
(an 8 MB file) with the exact expected SHA-256 hash.

## Verification

    python3 -m pytest /app/step_2/files/tests.py -v

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test or verifier files.
