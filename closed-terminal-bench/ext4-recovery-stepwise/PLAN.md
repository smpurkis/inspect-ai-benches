# ext4 Recovery Stepwise Plan

This benchmark is a staged filesystem forensics and recovery task centered on a
partially corrupted ext4 disk image. The task forces the model to inspect and
repair the image, recover staged source material, and complete a deterministic
build-and-report pipeline from the recovered data.


## Benchmark Summary

Suggested task name:

- `ext4-recovery-stepwise`

Core idea:

- Step 1 recovers a mountable ext4 image and validates restored contents.
- Step 2 rebuilds a recovered Go extractor and uses it to unpack a second-stage
  workspace.
- Step 3 compiles and runs the second-stage toolchain to produce a canonical
  manifest and checksum report.


## 3-Step Structure

### Step 1: Repair And Mount Image

Objective:

- Repair a partially corrupted ext4 image so it mounts read-only and exposes the
  hidden project tree.

What it tests:

- filesystem inspection
- low-level repair workflow
- safe mount practices
- hash-based verification

Verification:

- image mounts read-only
- expected directory tree appears
- known files match reference hashes exactly
- any mount or hash failure scores zero for the step

Implementation notes:

- build a Docker environment with `e2fsprogs`, `mount`, `debugfs`, `losetup`
- visible tests should exercise only the published hashes/tree
- hidden tests should vary corruption shape or check extra files already
  implied by the recovered tree


### Step 2: Recover And Rebuild Extractor

Objective:

- Recover a Go archive extractor from the restored source tree and run it
  against an embedded payload.

What it tests:

- source recovery from repaired filesystem
- Go build repair
- deterministic extraction behavior

Verification:

- extractor builds successfully
- output workspace matches reference tree byte for byte
- all sentinel files are present and unmodified

Implementation notes:

- keep the payload embedded in recovered assets
- expose one public output tree and one hidden one
- use tree hash + sentinel checks + file-by-file comparison


### Step 3: Compile And Run Second-Stage Toolchain

Objective:

- Compile the recovered second-stage toolchain and generate a deterministic
  manifest/checksum report over the restored data.

What it tests:

- full recovery chain correctness
- deterministic reporting
- exact formatting

Verification:

- manifest format matches exactly
- checksums match hidden reference set exactly
- any missing/extra entry or checksum mismatch scores zero

Implementation notes:

- keep manifest format strict and line-oriented
- prefer a visible sample manifest plus hidden full reference
- tests should compare both structure and content


## Why This Benchmark Is Good

- combines filesystem repair, build recovery, and deterministic reporting
- staged progression makes failures interpretable
- hidden tests can remain fair by varying corruption, not changing task goals


## Suggested Folder Layout

```text
ext4-recovery-stepwise/
  PLAN.md
  eval.yaml
  run.py
  compose.yaml
  environment/
    Dockerfile
  steps/
    step_1/
    step_2/
    step_3/
```


## Final Recommendation

This is a strong terminal benchmark because it mixes repair, build, and exact
artifact verification without requiring network access or arbitrary creativity.
