#!/usr/bin/env python3
"""Generate a corrupted ext4 disk image and reference data for ext4-recovery-stepwise.

This script is the SINGLE SOURCE OF TRUTH for all file contents and reference
hashes. It runs during Docker build to create:
  - /app/disk.img           (corrupted ext4 image)
  - /app/references/step*/  (JSON reference files for tests)
"""

import gzip
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import tarfile
import tempfile

# ── Image configuration ──────────────────────────────────────────────────
IMAGE_PATH = "/app/disk.img"
IMAGE_SIZE_MB = 64
BLOCK_SIZE = 1024
REFERENCES_DIR = "/app/references"

# ── Disk image file contents ─────────────────────────────────────────────

README_MD = """\
# Recovery Project

This project contains an extractor tool that processes compressed payloads
and produces a workspace directory.

## Building

    cd src && go build -o ../extractor .

## Usage

    ./extractor <payload.tar.gz> <output_dir>

## Structure

- src/       Go source code for the extractor
- lib/       Utility library functions
- data/      Payload and corpus data
- config/    Configuration files
- docs/      Project documentation
- tests/     Test files
- scripts/   Build and helper scripts
"""

SETTINGS_JSON = """\
{
  "version": "1.2.0",
  "extractor": {
    "buffer_size": 8192,
    "max_file_size": 10485760,
    "allow_overwrite": false
  },
  "output": {
    "directory": "/tmp/workspace",
    "preserve_permissions": true
  },
  "logging": {
    "level": "info",
    "format": "json"
  }
}
"""

GO_MOD = """\
module recovery/extractor

go 1.21
"""

# Five bugs in the extractor:
#   BUG 1 (syntax):  missing closing } for the for-loop  (line ~70)
#   BUG 2 (logic):   cleanName = cleanName[1:]  strips the first character
#   BUG 3 (logic):   os.O_APPEND instead of os.O_TRUNC in extractFile
#   BUG 4 (logic):   io.LimitReader(r, 4*1024*1024-1) truncates files
#                    exactly 4 MB by 1 byte (off-by-one)
#   BUG 5 (non-determinism): accumulate files in map[string][]byte before
#                    writing — map iteration order is non-deterministic
EXTRACTOR_GO = (
    "package main\n"
    "\n"
    "import (\n"
    "\t\"archive/tar\"\n"
    "\t\"compress/gzip\"\n"
    "\t\"fmt\"\n"
    "\t\"io\"\n"
    "\t\"os\"\n"
    "\t\"path/filepath\"\n"
    ")\n"
    "\n"
    "func main() {\n"
    "\tif len(os.Args) != 3 {\n"
    "\t\tfmt.Fprintf(os.Stderr, \"Usage: %s <payload.tar.gz> <output_dir>\\n\", os.Args[0])\n"
    "\t\tos.Exit(1)\n"
    "\t}\n"
    "\n"
    "\tpayloadPath := os.Args[1]\n"
    "\toutputDir := os.Args[2]\n"
    "\n"
    "\tif err := extractPayload(payloadPath, outputDir); err != nil {\n"
    "\t\tfmt.Fprintf(os.Stderr, \"extraction failed: %v\\n\", err)\n"
    "\t\tos.Exit(1)\n"
    "\t}\n"
    "\n"
    "\tfmt.Printf(\"Successfully extracted to %s\\n\", outputDir)\n"
    "}\n"
    "\n"
    "func extractPayload(archivePath, destDir string) error {\n"
    "\tfile, err := os.Open(archivePath)\n"
    "\tif err != nil {\n"
    "\t\treturn fmt.Errorf(\"cannot open archive: %w\", err)\n"
    "\t}\n"
    "\tdefer file.Close()\n"
    "\n"
    "\tgzReader, err := gzip.NewReader(file)\n"
    "\tif err != nil {\n"
    "\t\treturn fmt.Errorf(\"invalid gzip stream: %w\", err)\n"
    "\t}\n"
    "\tdefer gzReader.Close()\n"
    "\n"
    "\ttarReader := tar.NewReader(gzReader)\n"
    "\n"
    "\t// BUG 5: accumulate all file contents in a map before writing;\n"
    "\t// map iteration order is non-deterministic in Go.\n"
    "\tfileContents := make(map[string][]byte)\n"
    "\tfileModes := make(map[string]os.FileMode)\n"
    "\tdirPaths := []string{}\n"
    "\n"
    "\tfor {\n"
    "\t\theader, err := tarReader.Next()\n"
    "\t\tif err == io.EOF {\n"
    "\t\t\tbreak\n"
    "\t\t}\n"
    "\t\tif err != nil {\n"
    "\t\t\treturn fmt.Errorf(\"reading tar entry: %w\", err)\n"
    "\t\t}\n"
    "\n"
    "\t\tcleanName := header.Name\n"
    "\t\tif len(cleanName) > 0 {\n"
    "\t\t\tcleanName = cleanName[1:]\n"
    "\t\t}\n"
    "\n"
    "\t\ttargetPath := filepath.Join(destDir, cleanName)\n"
    "\n"
    "\t\tswitch header.Typeflag {\n"
    "\t\tcase tar.TypeDir:\n"
    "\t\t\tdirPaths = append(dirPaths, targetPath)\n"
    "\t\tcase tar.TypeReg:\n"
    "\t\t\t// BUG 4: LimitReader with 4MB-1 truncates files exactly 4 MB\n"
    "\t\t\t// by one byte (off-by-one error).\n"
    "\t\t\tlimited := io.LimitReader(tarReader, 4*1024*1024-1)\n"
    "\t\t\tdata, err := io.ReadAll(limited)\n"
    "\t\t\tif err != nil {\n"
    "\t\t\t\treturn fmt.Errorf(\"reading entry %s: %w\", header.Name, err)\n"
    "\t\t\t}\n"
    "\t\t\tfileContents[targetPath] = data\n"
    "\t\t\tfileModes[targetPath] = header.FileInfo().Mode()\n"
    "\t\tdefault:\n"
    "\t\t\tfmt.Fprintf(os.Stderr, \"skipping unsupported type %d for %s\\n\",\n"
    "\t\t\t\theader.Typeflag, header.Name)\n"
    "\t\t}\n"
    "\n"
    "\treturn nil\n"
    "}\n"
    "\n"
    "\t// Create directories first\n"
    "\tfor _, d := range dirPaths {\n"
    "\t\tif err := os.MkdirAll(d, 0755); err != nil {\n"
    "\t\t\treturn fmt.Errorf(\"creating directory %s: %w\", d, err)\n"
    "\t\t}\n"
    "\t}\n"
    "\n"
    "\t// BUG 5 continued: iterate over map (non-deterministic order)\n"
    "\tfor targetPath, data := range fileContents {\n"
    "\t\tif err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {\n"
    "\t\t\treturn err\n"
    "\t\t}\n"
    "\t\tif err := extractFile(targetPath, data, fileModes[targetPath]); err != nil {\n"
    "\t\t\treturn err\n"
    "\t\t}\n"
    "\t}\n"
    "\treturn nil\n"
    "}\n"
    "\n"
    "func extractFile(destPath string, data []byte, mode os.FileMode) error {\n"
    "\toutFile, err := os.OpenFile(destPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, mode)\n"
    "\tif err != nil {\n"
    "\t\treturn fmt.Errorf(\"creating file %s: %w\", destPath, err)\n"
    "\t}\n"
    "\tdefer outFile.Close()\n"
    "\n"
    "\tif _, err := outFile.Write(data); err != nil {\n"
    "\t\treturn fmt.Errorf(\"writing file %s: %w\", destPath, err)\n"
    "\t}\n"
    "\n"
    "\treturn nil\n"
    "}\n"
)

UTILS_GO = (
    "package main\n"
    "\n"
    "import (\n"
    "\t\"crypto/sha256\"\n"
    "\t\"encoding/hex\"\n"
    "\t\"fmt\"\n"
    "\t\"io\"\n"
    "\t\"os\"\n"
    ")\n"
    "\n"
    "// FileHash computes the SHA-256 hash of a file at the given path.\n"
    "func FileHash(path string) (string, error) {\n"
    "\tf, err := os.Open(path)\n"
    "\tif err != nil {\n"
    "\t\treturn \"\", fmt.Errorf(\"open %s: %w\", path, err)\n"
    "\t}\n"
    "\tdefer f.Close()\n"
    "\n"
    "\th := sha256.New()\n"
    "\tif _, err := io.Copy(h, f); err != nil {\n"
    "\t\treturn \"\", fmt.Errorf(\"hash %s: %w\", path, err)\n"
    "\t}\n"
    "\n"
    "\treturn hex.EncodeToString(h.Sum(nil)), nil\n"
    "}\n"
    "\n"
    "// FormatSize returns a human-readable size string.\n"
    "func FormatSize(bytes int64) string {\n"
    "\tconst unit = 1024\n"
    "\tif bytes < unit {\n"
    "\t\treturn fmt.Sprintf(\"%d B\", bytes)\n"
    "\t}\n"
    "\tdiv, exp := int64(unit), 0\n"
    "\tfor n := bytes / unit; n >= unit; n /= unit {\n"
    "\t\tdiv *= unit\n"
    "\t\texp++\n"
    "\t}\n"
    "\treturn fmt.Sprintf(\"%.1f %cB\", float64(bytes)/float64(div), \"KMGTPE\"[exp])\n"
    "}\n"
)

DESIGN_MD = """\
# Extractor Design Document

## Overview

The extractor tool processes compressed tar.gz payloads and produces
a workspace directory containing the extracted contents.

## Architecture

1. Input: A gzip-compressed tar archive
2. Processing: Stream decompression and extraction
3. Output: Directory tree with extracted files

## Error Handling

- Invalid gzip: returns descriptive error
- Corrupt tar: returns entry-level error
- Permission denied: propagates OS error
- Missing output dir: creates with MkdirAll

## Future Work

- Support for zip and bz2 formats
- Parallel extraction for large archives
- Checksum verification during extraction
"""

API_MD = """\
# Extractor API Reference

## Command Line Interface

    extractor <payload> <output_dir>

### Arguments

  payload     - Path to .tar.gz archive
  output_dir  - Directory where files are extracted

### Exit Codes

  0  Success
  1  Error (see stderr)

### Examples

    ./extractor data/payload.tar.gz /tmp/workspace
    ./extractor /app/data/payload.tar.gz /app/workspace
"""

EXTRACTOR_TEST_GO = (
    "package main\n"
    "\n"
    "import (\n"
    "\t\"os\"\n"
    "\t\"testing\"\n"
    ")\n"
    "\n"
    "func TestExtractorSourceExists(t *testing.T) {\n"
    "\tif _, err := os.Stat(\"extractor.go\"); os.IsNotExist(err) {\n"
    "\t\tt.Fatal(\"extractor.go not found\")\n"
    "\t}\n"
    "}\n"
    "\n"
    "func TestGoModExists(t *testing.T) {\n"
    "\tif _, err := os.Stat(\"go.mod\"); os.IsNotExist(err) {\n"
    "\t\tt.Fatal(\"go.mod not found\")\n"
    "\t}\n"
    "}\n"
)

BUILD_SH = """\
#!/bin/sh
set -e
cd "$(dirname "$0")/../src"
go build -o ../bin/extractor .
echo "Build complete: bin/extractor"
"""

NESTED_TXT = """\
This file is deeply nested for recovery testing purposes.
Path: project/deep/level1/level2/level3/level4/level5/nested.txt
If you can read this, the deep directory structure was recovered successfully.
"""


def generate_corpus() -> bytes:
    """Generate a deterministic ~1.4MB corpus file."""
    return b"".join(
        f"CORPUS_DATA_LINE_{i:06d}\n".encode() for i in range(60000)
    )


def generate_large_corpus() -> bytes:
    """Generate a deterministic 8MB large corpus file with repeating pattern."""
    # 8 MB = 8 * 1024 * 1024 = 8388608 bytes
    target = 8 * 1024 * 1024
    pattern = b"LARGE_CORPUS_PATTERN_8MB_RECOVERY_BENCHMARK_"
    # Build repeating pattern up to target size
    repeats = target // len(pattern) + 1
    return (pattern * repeats)[:target]


# ── Workspace files (contents of payload.tar.gz) ────────────────────────

# New manifest_tool.go with two deliberate bugs for the Merkle tree task:
#   BUG A: sorts children by hash instead of by name before hashing a
#          directory node (produces wrong Merkle root)
#   BUG B: doesn't include directory entries in the output (only files)
# The agent must fix both bugs.
WS_MANIFEST_TOOL_GO = (
    "package main\n"
    "\n"
    "import (\n"
    "\t\"crypto/sha256\"\n"
    "\t\"encoding/hex\"\n"
    "\t\"fmt\"\n"
    "\t\"io\"\n"
    "\t\"os\"\n"
    "\t\"path/filepath\"\n"
    "\t\"sort\"\n"
    ")\n"
    "\n"
    "// entry holds a single manifest entry (file or directory).\n"
    "type entry struct {\n"
    "\trelPath string // relative path from workspace root\n"
    "\thash    string // SHA-256 hex\n"
    "\tisDir   bool\n"
    "}\n"
    "\n"
    "func main() {\n"
    "\tif len(os.Args) < 2 {\n"
    "\t\tfmt.Fprintf(os.Stderr, \"Usage: %s <directory> [output_file]\\n\", os.Args[0])\n"
    "\t\tos.Exit(1)\n"
    "\t}\n"
    "\n"
    "\tdir := os.Args[1]\n"
    "\tentries, rootHash, err := buildMerkleManifest(dir)\n"
    "\tif err != nil {\n"
    "\t\tfmt.Fprintf(os.Stderr, \"error: %v\\n\", err)\n"
    "\t\tos.Exit(1)\n"
    "\t}\n"
    "\n"
    "\tvar out *os.File\n"
    "\tvar createErr error\n"
    "\tif len(os.Args) >= 3 {\n"
    "\t\tout, createErr = os.Create(os.Args[2])\n"
    "\t\tif createErr != nil {\n"
    "\t\t\tfmt.Fprintf(os.Stderr, \"cannot create output file: %v\\n\", createErr)\n"
    "\t\t\tos.Exit(1)\n"
    "\t\t}\n"
    "\t\tdefer out.Close()\n"
    "\t} else {\n"
    "\t\tout = os.Stdout\n"
    "\t}\n"
    "\n"
    "\t// First line: root hash\n"
    "\tfmt.Fprintln(out, rootHash)\n"
    "\n"
    "\t// BUG B: only emit file entries, skip directories\n"
    "\tfor _, e := range entries {\n"
    "\t\tif e.isDir {\n"
    "\t\t\tcontinue // BUG B: should output dir entries too\n"
    "\t\t}\n"
    "\t\tfmt.Fprintf(out, \"%s  %s\\n\", e.hash, e.relPath)\n"
    "\t}\n"
    "}\n"
    "\n"
    "// hashFile returns the SHA-256 of a regular file.\n"
    "func hashFile(path string) (string, error) {\n"
    "\tf, err := os.Open(path)\n"
    "\tif err != nil {\n"
    "\t\treturn \"\", err\n"
    "\t}\n"
    "\tdefer f.Close()\n"
    "\th := sha256.New()\n"
    "\tif _, err := io.Copy(h, f); err != nil {\n"
    "\t\treturn \"\", err\n"
    "\t}\n"
    "\treturn hex.EncodeToString(h.Sum(nil)), nil\n"
    "}\n"
    "\n"
    "// hashDir computes the Merkle hash of a directory node.\n"
    "// It concatenates `name\\0hash\\n` for each child and hashes the result.\n"
    "// BUG A: children are sorted by hash instead of by name.\n"
    "func hashDir(children []struct{ name, hash string }) string {\n"
    "\t// BUG A: sort by hash value rather than by child name\n"
    "\tsort.Slice(children, func(i, j int) bool {\n"
    "\t\treturn children[i].hash < children[j].hash\n"
    "\t})\n"
    "\tvar buf []byte\n"
    "\tfor _, c := range children {\n"
    "\t\tbuf = append(buf, []byte(c.name+\"\\x00\"+c.hash+\"\\n\")...)\n"
    "\t}\n"
    "\th := sha256.Sum256(buf)\n"
    "\treturn hex.EncodeToString(h[:])\n"
    "}\n"
    "\n"
    "// buildMerkleManifest walks dir and builds a Merkle tree manifest.\n"
    "// Returns sorted entries and the root directory hash.\n"
    "func buildMerkleManifest(root string) ([]entry, string, error) {\n"
    "\t// Collect all paths first\n"
    "\ttype nodeInfo struct {\n"
    "\t\tabsPath string\n"
    "\t\trelPath string\n"
    "\t\tisDir   bool\n"
    "\t}\n"
    "\tvar nodes []nodeInfo\n"
    "\terr := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {\n"
    "\t\tif err != nil {\n"
    "\t\t\treturn err\n"
    "\t\t}\n"
    "\t\trel, err := filepath.Rel(root, path)\n"
    "\t\tif err != nil {\n"
    "\t\t\treturn err\n"
    "\t\t}\n"
    "\t\tif rel == \".\" {\n"
    "\t\t\treturn nil // skip root itself\n"
    "\t\t}\n"
    "\t\tnodes = append(nodes, nodeInfo{path, rel, info.IsDir()})\n"
    "\t\treturn nil\n"
    "\t})\n"
    "\tif err != nil {\n"
    "\t\treturn nil, \"\", err\n"
    "\t}\n"
    "\n"
    "\t// Build bottom-up: compute file hashes, then directory hashes\n"
    "\thashCache := make(map[string]string) // absPath -> hash\n"
    "\n"
    "\t// First pass: hash all files\n"
    "\tfor _, n := range nodes {\n"
    "\t\tif !n.isDir {\n"
    "\t\t\th, err := hashFile(n.absPath)\n"
    "\t\t\tif err != nil {\n"
    "\t\t\t\treturn nil, \"\", err\n"
    "\t\t\t}\n"
    "\t\t\thashCache[n.absPath] = h\n"
    "\t\t}\n"
    "\t}\n"
    "\n"
    "\t// Second pass: hash directories bottom-up (deepest first)\n"
    "\t// Walk gives us top-down order; reverse for bottom-up\n"
    "\tfor i := len(nodes) - 1; i >= 0; i-- {\n"
    "\t\tn := nodes[i]\n"
    "\t\tif !n.isDir {\n"
    "\t\t\tcontinue\n"
    "\t\t}\n"
    "\t\t// Collect immediate children\n"
    "\t\tvar children []struct{ name, hash string }\n"
    "\t\tfor _, child := range nodes {\n"
    "\t\t\tchildDir := filepath.Dir(child.absPath)\n"
    "\t\t\tif childDir == n.absPath {\n"
    "\t\t\t\tchildren = append(children, struct{ name, hash string }{\n"
    "\t\t\t\t\tname: filepath.Base(child.absPath),\n"
    "\t\t\t\t\thash: hashCache[child.absPath],\n"
    "\t\t\t\t})\n"
    "\t\t\t}\n"
    "\t\t}\n"
    "\t\thashCache[n.absPath] = hashDir(children)\n"
    "\t}\n"
    "\n"
    "\t// Compute root hash (hash of the root directory's children)\n"
    "\tvar rootChildren []struct{ name, hash string }\n"
    "\tfor _, n := range nodes {\n"
    "\t\tif filepath.Dir(n.absPath) == root {\n"
    "\t\t\trootChildren = append(rootChildren, struct{ name, hash string }{\n"
    "\t\t\t\tname: filepath.Base(n.absPath),\n"
    "\t\t\t\thash: hashCache[n.absPath],\n"
    "\t\t\t})\n"
    "\t\t}\n"
    "\t}\n"
    "\trootHash := hashDir(rootChildren)\n"
    "\n"
    "\t// Build output entries (sorted by relPath)\n"
    "\tvar entries []entry\n"
    "\tfor _, n := range nodes {\n"
    "\t\trelPath := n.relPath\n"
    "\t\tif n.isDir {\n"
    "\t\t\trelPath = relPath + \"/\"\n"
    "\t\t}\n"
    "\t\tentries = append(entries, entry{\n"
    "\t\t\trelPath: relPath,\n"
    "\t\t\thash:    hashCache[n.absPath],\n"
    "\t\t\tisDir:   n.isDir,\n"
    "\t\t})\n"
    "\t}\n"
    "\tsort.Slice(entries, func(i, j int) bool {\n"
    "\t\treturn entries[i].relPath < entries[j].relPath\n"
    "\t})\n"
    "\n"
    "\treturn entries, rootHash, nil\n"
    "}\n"
)

WS_GO_MOD = """\
module recovery/toolchain

go 1.21
"""

WS_SENTINEL_ALPHA = "ALPHA_SENTINEL_2024_RECOVERY\n"

WS_SENTINEL_BETA = "BETA_SENTINEL_2024_RECOVERY\n"

WS_SENTINEL_GAMMA = (
    b"\x89PNG\r\n\x1a\n"
    b"FAKE_PNG_SENTINEL_DATA_FOR_RECOVERY_BENCHMARK"
    b"\x00\x00\x00\x00"
)

WS_BUILD_JSON = """\
{
  "name": "recovery-toolchain",
  "version": "0.1.0",
  "target": "manifest",
  "options": {
    "deterministic": true,
    "hash_algorithm": "sha256"
  }
}
"""

WS_README = """\
# Recovery Workspace

This workspace was extracted from the disk image payload.

## Contents

- data/       Sentinel and test data files
- config/     Build configuration
"""


def generate_large_corpus_ws() -> bytes:
    """Generate a deterministic 8MB large_corpus.dat for the workspace payload."""
    return generate_large_corpus()


# Maps tar-internal relative paths to content bytes.
# NOTE: large_corpus.dat is added for step 2 bug 4 (4MB truncation) testing.
def build_workspace_files() -> dict:
    large_corpus = generate_large_corpus_ws()
    return {
        "README.md": WS_README.encode(),
        "config/build.json": WS_BUILD_JSON.encode(),
        "data/large_corpus.dat": large_corpus,
        "data/sentinel_alpha.txt": WS_SENTINEL_ALPHA.encode(),
        "data/sentinel_beta.txt": WS_SENTINEL_BETA.encode(),
        "data/sentinel_gamma.bin": WS_SENTINEL_GAMMA,
    }


WORKSPACE_DIRS = ["config", "data"]

# Directories to create in the ext4 image (order matters — parents first).
DISK_DIRS = [
    "project",
    "project/config",
    "project/data",
    "project/deep",
    "project/deep/level1",
    "project/deep/level1/level2",
    "project/deep/level1/level2/level3",
    "project/deep/level1/level2/level3/level4",
    "project/deep/level1/level2/level3/level4/level5",
    "project/docs",
    "project/lib",
    "project/scripts",
    "project/src",
    "project/tests",
]

DISK_SYMLINKS = {
    "project/src/README": "../../README.md",
    "project/latest.json": "config/settings.json",
}


# ── Helper functions ─────────────────────────────────────────────────────

def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def create_payload_tar_gz(workspace_files: dict) -> bytes:
    """Create a deterministic tar.gz payload containing workspace files."""
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        for dirname in sorted(WORKSPACE_DIRS):
            info = tarfile.TarInfo(name=dirname + "/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            tar.addfile(info)

        for filepath in sorted(workspace_files):
            content = workspace_files[filepath]
            info = tarfile.TarInfo(name=filepath)
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            tar.addfile(info, io.BytesIO(content))

    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb", mtime=0) as gz:
        gz.write(tar_buf.getvalue())
    return gz_buf.getvalue()


# ── Image creation ───────────────────────────────────────────────────────

def create_ext4_image(image_path: str) -> tuple[dict, dict]:
    """Create and populate a 64 MB ext4 image, then corrupt it.

    Returns a tuple of:
      - all_files: dict mapping filesystem paths to their content bytes
      - workspace_files: dict mapping workspace-relative paths to content bytes
    """
    subprocess.run(
        ["dd", "if=/dev/zero", f"of={image_path}",
         "bs=1M", f"count={IMAGE_SIZE_MB}"],
        check=True, capture_output=True,
    )

    # Disable metadata_csum so that targeted field corruption does not
    # break superblock/group-descriptor CRCs (keeps the task about repair,
    # not about re-computing ext4 checksums).
    subprocess.run(
        ["mke2fs", "-t", "ext4", "-b", str(BLOCK_SIZE),
         "-O", "^metadata_csum", "-F", image_path],
        check=True, capture_output=True,
    )

    workspace_files = build_workspace_files()
    payload_data = create_payload_tar_gz(workspace_files)
    corpus_data = generate_corpus()

    all_files: dict[str, bytes] = {
        "project/README.md": README_MD.encode(),
        "project/config/settings.json": SETTINGS_JSON.encode(),
        "project/data/corpus.dat": corpus_data,
        "project/data/payload.tar.gz": payload_data,
        "project/deep/level1/level2/level3/level4/level5/nested.txt": NESTED_TXT.encode(),
        "project/docs/api.md": API_MD.encode(),
        "project/docs/design.md": DESIGN_MD.encode(),
        "project/lib/utils.go": UTILS_GO.encode(),
        "project/scripts/build.sh": BUILD_SH.encode(),
        "project/src/extractor.go": EXTRACTOR_GO.encode(),
        "project/src/go.mod": GO_MOD.encode(),
        "project/tests/extractor_test.go": EXTRACTOR_TEST_GO.encode(),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_paths: dict[str, str] = {}
        for fspath, content in all_files.items():
            safe = fspath.replace("/", "__")
            tmp = os.path.join(tmpdir, safe)
            with open(tmp, "wb") as fh:
                fh.write(content)
            temp_paths[fspath] = tmp

        cmds: list[str] = []

        for d in DISK_DIRS:
            cmds.append(f"mkdir {d}")

        for fspath in sorted(all_files):
            cmds.append(f"write {temp_paths[fspath]} {fspath}")

        for link, target in DISK_SYMLINKS.items():
            cmds.append(f"symlink {link} {target}")

        cmds.append("set_inode_field project/scripts/build.sh mode 0100755")

        proc = subprocess.run(
            ["debugfs", "-w", image_path],
            input="\n".join(cmds) + "\n",
            capture_output=True, text=True,
        )
        # debugfs may return non-zero even on success; log stderr for debugging
        if proc.stderr:
            for line in proc.stderr.splitlines():
                if "error" in line.lower() and "filesystem" not in line.lower():
                    print(f"  debugfs warning: {line}", file=sys.stderr)

    corrupt_image(image_path)
    return all_files, workspace_files


def corrupt_image(image_path: str) -> None:
    """Apply targeted metadata corruption that e2fsck can fully repair.

    Corruptions:
      1. Set s_state to EXT4_ERROR_FS (forces full check)
      2. Corrupt bg_free_blocks_count_lo in the primary group descriptor
      3. Corrupt bg_free_inodes_count_lo in the primary group descriptor
      4. Zero out the backup superblock at block group 1 (block 8193)
         for a 1K-block ext4 filesystem.
      5. Zero out the backup superblock at block group 2 (block 16385)
         for a 1K-block ext4 filesystem. This removes a second backup,
         forcing the agent to locate a valid backup (e.g. block group 4
         at block 32768) using `dumpe2fs` and repair with `e2fsck -b`.
      6. Corrupt the inode for project/data/corpus.dat by zeroing its
         mode bits via debugfs, making the file appear missing/broken.
         The agent must use `e2fsck -f` or `debugfs` to restore it.
    """
    with open(image_path, "r+b") as f:
        # 1. Superblock s_state at offset 1024 + 0x3A = 1082
        f.seek(1024 + 0x3A)
        f.write(struct.pack("<H", 2))  # EXT4_ERROR_FS

        # 2. Group descriptor table starts at block 2 (offset 2048).
        #    bg_free_blocks_count_lo is at byte 12 within each 32-byte descriptor.
        f.seek(2048 + 12)
        val = struct.unpack("<H", f.read(2))[0]
        f.seek(2048 + 12)
        f.write(struct.pack("<H", val ^ 0x00FF))

        # 3. bg_free_inodes_count_lo at byte 14
        f.seek(2048 + 14)
        val = struct.unpack("<H", f.read(2))[0]
        f.seek(2048 + 14)
        f.write(struct.pack("<H", val ^ 0x00FF))

        # 4. Backup superblock in block group 1 (block 8193 for 1K-block fs).
        #    Zeroing 1024 bytes at this offset destroys the group 1 backup.
        backup1_offset = 8193 * BLOCK_SIZE
        f.seek(0, 2)  # seek to end to get size
        size = f.tell()
        if backup1_offset + 1024 <= size:
            f.seek(backup1_offset)
            f.write(b"\x00" * 1024)

        # 5. Backup superblock in block group 2 (block 16385 for 1K-block fs).
        #    With both group-1 and group-2 backups zeroed the agent must find
        #    the still-valid backup at block group 4 (block 32768) and run:
        #      e2fsck -b 32768 /app/disk.img
        #    Zeroing 1024 bytes at offset 16385 * BLOCK_SIZE.
        backup2_offset = 16385 * BLOCK_SIZE
        if backup2_offset + 1024 <= size:
            f.seek(backup2_offset)
            f.write(b"\x00" * 1024)

    # 6. Use debugfs to corrupt the inode for project/data/corpus.dat.
    #    Setting mode to 0 makes the file appear as type "unknown" / broken.
    #    After this the agent must run e2fsck -f to auto-repair the inode,
    #    or use debugfs manually to restore a sane mode (e.g. 0100644).
    proc = subprocess.run(
        ["debugfs", "-w", image_path],
        input="set_inode_field project/data/corpus.dat mode 0\n",
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"  corruption 6 warning: {proc.stderr}", file=sys.stderr)


# ── Reference file generation ────────────────────────────────────────────

def compute_merkle_manifest(workspace_files: dict) -> tuple[str, list[str]]:
    """Compute the CORRECT Merkle tree manifest for workspace_files.

    The workspace has this structure (from WORKSPACE_DIRS + workspace_files):
      config/
        build.json
      data/
        large_corpus.dat
        sentinel_alpha.txt
        sentinel_beta.txt
        sentinel_gamma.bin
      README.md

    Directory hash = SHA-256 of concatenated children sorted BY NAME:
      name\\0hash\\n  for each child

    Returns (root_hash, sorted_lines) where sorted_lines are all entries
    after the root hash line, sorted lexicographically by path.
    """
    # Build virtual filesystem tree
    # File hashes
    file_hashes = {path: sha256hex(content) for path, content in workspace_files.items()}

    def dir_hash(children: list[tuple[str, str]]) -> str:
        """Hash a directory node from a list of (name, child_hash) sorted by name."""
        children_sorted = sorted(children, key=lambda c: c[0])
        buf = b""
        for name, h in children_sorted:
            buf += (name + "\x00" + h + "\n").encode()
        return sha256hex(buf)

    # Compute directory hashes bottom-up
    # Known directory structure:
    # config: {build.json}
    # data: {large_corpus.dat, sentinel_alpha.txt, sentinel_beta.txt, sentinel_gamma.bin}
    # root: {README.md, config/, data/}

    config_children = [("build.json", file_hashes["config/build.json"])]
    config_h = dir_hash(config_children)

    data_children = [
        ("large_corpus.dat", file_hashes["data/large_corpus.dat"]),
        ("sentinel_alpha.txt", file_hashes["data/sentinel_alpha.txt"]),
        ("sentinel_beta.txt", file_hashes["data/sentinel_beta.txt"]),
        ("sentinel_gamma.bin", file_hashes["data/sentinel_gamma.bin"]),
    ]
    data_h = dir_hash(data_children)

    root_children = [
        ("README.md", file_hashes["README.md"]),
        ("config", config_h),
        ("data", data_h),
    ]
    root_h = dir_hash(root_children)

    # Build all manifest lines (after root hash line)
    lines = []
    # Files
    for path, h in file_hashes.items():
        lines.append(f"{h}  {path}")
    # Directories
    lines.append(f"{config_h}  config/")
    lines.append(f"{data_h}  data/")

    lines.sort()
    return root_h, lines


def generate_references(all_files: dict, workspace_files: dict) -> None:
    """Write all reference JSON/text files used by the test suite."""
    for sub in ("step1", "step2", "step3"):
        os.makedirs(f"{REFERENCES_DIR}/{sub}", exist_ok=True)

    # ── Step 1 ──

    disk_tree = sorted(all_files.keys())
    _write_json(f"{REFERENCES_DIR}/step1/reference_tree.json", {
        "files": disk_tree,
    })

    # Public hashes: a small well-known subset
    public_hash_keys = [
        "project/README.md",
        "project/config/settings.json",
        "project/src/go.mod",
    ]
    _write_json(f"{REFERENCES_DIR}/step1/reference_hashes.json", {
        k: sha256hex(all_files[k]) for k in public_hash_keys
    })

    # Hidden: every file hash
    _write_json(f"{REFERENCES_DIR}/step1/hidden_hashes.json", {
        k: sha256hex(v) for k, v in sorted(all_files.items())
    })

    # Hidden: expected permissions (octal string)
    perms: dict[str, str] = {}
    for k in sorted(all_files):
        perms[k] = "0755" if k == "project/scripts/build.sh" else "0644"
    _write_json(f"{REFERENCES_DIR}/step1/hidden_permissions.json", perms)

    # Hidden: symlink targets
    _write_json(f"{REFERENCES_DIR}/step1/hidden_symlinks.json", DISK_SYMLINKS)

    # Hidden: directory metadata
    _write_json(f"{REFERENCES_DIR}/step1/hidden_dir_info.json", {
        "count": len(DISK_DIRS),
        "dirs": sorted(DISK_DIRS),
    })

    # Step 1 new references for backup superblock and inode repair
    # The valid backup superblock block number (block group 4 for 1K-block fs)
    with open(f"{REFERENCES_DIR}/step1/backup_superblock_group.txt", "w") as fh:
        fh.write("32768\n")

    # ── Step 2 ──

    ws_tree = sorted(workspace_files.keys())
    _write_json(f"{REFERENCES_DIR}/step2/workspace_tree.json", {
        "files": ws_tree,
    })

    _write_json(f"{REFERENCES_DIR}/step2/sentinel_hashes.json", {
        "data/sentinel_alpha.txt": sha256hex(workspace_files["data/sentinel_alpha.txt"]),
    })

    _write_json(f"{REFERENCES_DIR}/step2/workspace_hashes.json", {
        k: sha256hex(v) for k, v in sorted(workspace_files.items())
    })

    _write_json(f"{REFERENCES_DIR}/step2/workspace_file_count.json", {
        "count": len(workspace_files),
    })

    # ── Step 3 — Merkle tree manifest ──

    root_hash, manifest_lines = compute_merkle_manifest(workspace_files)

    # Full manifest text: root hash on line 1, then sorted entries
    manifest_text = root_hash + "\n" + "\n".join(manifest_lines) + "\n"

    # Public: root hash line + first 3 file entries (so agents can verify format)
    with open(f"{REFERENCES_DIR}/step3/manifest_public.txt", "w") as fh:
        fh.write(root_hash + "\n")
        fh.write("\n".join(manifest_lines[:3]) + "\n")

    # Hidden: full manifest
    with open(f"{REFERENCES_DIR}/step3/manifest_reference.txt", "w") as fh:
        fh.write(manifest_text)

    with open(f"{REFERENCES_DIR}/step3/manifest_hash.txt", "w") as fh:
        fh.write(sha256hex(manifest_text.encode()) + "\n")

    # Total line count: 1 (root) + len(manifest_lines)
    total_lines = 1 + len(manifest_lines)
    with open(f"{REFERENCES_DIR}/step3/manifest_entry_count.txt", "w") as fh:
        fh.write(str(total_lines) + "\n")

    # Store individual directory hashes for hidden tests
    # Recompute for reference storage
    file_hashes = {path: sha256hex(content) for path, content in workspace_files.items()}

    def dir_hash_ref(children: list[tuple[str, str]]) -> str:
        children_sorted = sorted(children, key=lambda c: c[0])
        buf = b""
        for name, h in children_sorted:
            buf += (name + "\x00" + h + "\n").encode()
        return sha256hex(buf)

    config_h = dir_hash_ref([("build.json", file_hashes["config/build.json"])])
    data_h = dir_hash_ref([
        ("large_corpus.dat", file_hashes["data/large_corpus.dat"]),
        ("sentinel_alpha.txt", file_hashes["data/sentinel_alpha.txt"]),
        ("sentinel_beta.txt", file_hashes["data/sentinel_beta.txt"]),
        ("sentinel_gamma.bin", file_hashes["data/sentinel_gamma.bin"]),
    ])

    _write_json(f"{REFERENCES_DIR}/step3/dir_hashes.json", {
        "config/": config_h,
        "data/": data_h,
    })


def _write_json(path: str, obj: object) -> None:
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


# ── Toolchain (written outside workspace so it is not self-hashing) ───

TOOLCHAIN_DIR = "/app/toolchain"


def write_toolchain_files() -> None:
    """Write the manifest_tool.go source to /app/toolchain/ (outside workspace).

    This prevents the self-referential hash problem: the tool that builds
    the Merkle manifest is NOT inside the directory it hashes.
    """
    os.makedirs(TOOLCHAIN_DIR, exist_ok=True)
    with open(os.path.join(TOOLCHAIN_DIR, "go.mod"), "w") as fh:
        fh.write(WS_GO_MOD)
    with open(os.path.join(TOOLCHAIN_DIR, "manifest_tool.go"), "w") as fh:
        fh.write(WS_MANIFEST_TOOL_GO)


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    os.makedirs(os.path.dirname(IMAGE_PATH), exist_ok=True)

    print("Creating ext4 disk image …")
    all_files, workspace_files = create_ext4_image(IMAGE_PATH)

    print("Writing toolchain files …")
    write_toolchain_files()

    print("Generating reference files …")
    generate_references(all_files, workspace_files)

    img_size = os.path.getsize(IMAGE_PATH)
    ref_count = sum(
        len(files) for _, _, files in os.walk(REFERENCES_DIR)
    )
    print(f"Done.  image={img_size} bytes  references={ref_count} files")


if __name__ == "__main__":
    main()
