# ext4 Recovery, Go Rebuild, and Merkle Manifest

Complete all three phases in sequence. Each phase depends on the previous.

---

## Phase 1: Repair the Corrupted ext4 Disk Image

A corrupted ext4 disk image is at `/app/disk.img`. Multiple kinds of metadata corruption have been applied -- the primary superblock, group descriptors, backup superblocks, and at least one file inode have been damaged.

Back up the image before attempting repairs. Repair the filesystem so that it passes a clean `e2fsck` check and all original files are accessible. Only repair metadata; do not alter file contents. Note that more than one backup superblock may be corrupted, so you will need to locate a valid one.

---

## Phase 2: Recover and Rebuild the Go Extractor

The repaired disk image contains a Go project. Mount or extract the source code from the image, identify and fix all bugs in the extractor program, build it, and run it to produce `/app/workspace/`.

The extractor processes a compressed tar archive found in the image's `project/data/` directory and extracts it to an output directory. There are multiple bugs across the source -- some prevent compilation, some produce incorrect output, and some cause non-determinism. You must find and fix all of them. The extractor binary should be placed at `/app/extractor`.

---

## Phase 3: Build Merkle Tree Manifest Tool

A Go program at `/app/toolchain/` builds a Merkle-tree manifest of a directory. It contains bugs. Fix all bugs, build the tool to `/app/manifest_tool`, and run it to produce `/app/manifest.txt` from `/app/workspace`.

### Manifest Format

The output file has the following format:

- Line 1: the Merkle root hash (SHA-256, 64 lowercase hex chars)
- Remaining lines: `<hash>  <relative_path>` for each file and directory entry, sorted lexicographically by path. Directory paths end with `/`.

The Merkle hash for a directory is computed by sorting its immediate children by name, then hashing the concatenation of `name\0hash\n` for each child (SHA-256).

Read the source carefully and ensure the tool correctly implements this specification.

## Verification

    python3 -m pytest /app/files/tests.py -v

## Constraints

- Work entirely offline inside the container.
- All outputs must be deterministic (identical across repeated runs).
- Do not modify test or verifier files.
