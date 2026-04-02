# Step 1: Repair and Recover ext4 Disk Image

A corrupted ext4 disk image is located at `/app/disk.img`. It contains a
project directory with Go source code, data files, and documentation.

**Important:** Back up the disk image before any repair attempt:
`cp /app/disk.img /app/disk.img.bak`

## Requirements

- Repair the corrupted ext4 filesystem so it passes a clean check.
- After repair, all files in the image should be accessible.
- Do not modify the actual file contents inside the image — only repair
  filesystem metadata.

## Hints

- `e2fsck` is the standard tool for checking and repairing ext4 filesystems.
- Use `debugfs` or `fuse2fs` to examine files inside the image without
  needing root mount privileges.
- `dumpe2fs` shows superblock and group descriptor information.

## Backup Superblock Recovery

The primary superblock may be damaged. Use `dumpe2fs -h /app/disk.img` to
check its state. If the primary superblock is corrupt or the filesystem state
is not clean, you can repair using a backup superblock.

To list all backup superblock locations:

    dumpe2fs /app/disk.img | grep -i "backup superblock"

Then repair using a backup (for example, block 32768). Use `-y` to automatically
answer "yes" to all repair prompts (required for non-interactive use):

    e2fsck -b 32768 -y /app/disk.img

You may need to try several backup block numbers if some backups are also
damaged. Common backup superblock locations for a 1K-block filesystem include
blocks 8193, 16385, 24577, 32768, 40961, …

## Inode Repair

One file inode may be corrupted — its mode bits may have been zeroed, making
the file appear as an unknown type. Use `e2fsck -f` to attempt automatic
repair:

    e2fsck -f /app/disk.img

For manual inspection and repair with debugfs:

    debugfs /app/disk.img
    > stat project/data/corpus.dat
    > set_inode_field project/data/corpus.dat mode 0100644

**Warning:** Do not delete or remove any directory entries — only repair
filesystem metadata. Deleting entries will cause data loss that cannot be
recovered.

## Verification

Tests at `/app/step_1/files/tests.py` verify the repair.

    python3 -m pytest /app/step_1/files/tests.py -v

Do NOT use `python3 tests.py` — test files require pytest.

## Scoring

- Step 1 fail -> 0
- Step 1 pass, Step 2 fail -> 1/3
- Step 1+2 pass, Step 3 fail -> 2/3
- All pass -> 1.0

## Constraints

- Work entirely offline inside the container.
- Keep outputs deterministic.
- Do not modify test or verifier files.
