"""Hidden tests for git secret forensics benchmark (14 tests).

These probe the hard-to-find secret locations that the visible tests don't cover:
git notes, stashes, reflog, orphaned objects, base64 encoding, split-across-lines,
replace refs, merge commit messages, hex encoding, custom refs, nested base64,
.gitattributes filter specs, dangling objects, and decoy preservation.
"""

from __future__ import annotations

import base64
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "files"))

import forensics_utils as utils


def test_hidden_not_in_git_notes() -> None:
    """No secret appears in any git note on any commit."""
    patterns = utils.read_patterns()

    # Check all notes refs
    result = utils.run_git("notes", "list", check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return  # No notes is fine — means they were removed

    for line in result.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        note_blob = parts[0]
        content = utils.object_content(note_blob)
        for pattern in patterns:
            assert pattern not in content, (
                f"Secret {pattern!r} found in git note blob {note_blob[:8]}"
            )

    # Also check via git log --notes
    result = utils.run_git("log", "--all", "--notes", "--format=%N", check=False)
    for pattern in patterns:
        assert pattern not in result.stdout, (
            f"Secret {pattern!r} found in git log --notes output"
        )


def test_hidden_not_in_stash() -> None:
    """No secret appears in any stash entry."""
    patterns = utils.read_patterns()

    result = utils.run_git("stash", "list", check=False)
    if not result.stdout.strip():
        return  # No stashes is fine

    for i, line in enumerate(result.stdout.strip().splitlines()):
        stash_ref = f"stash@{{{i}}}"
        # Check stash diff
        diff_result = utils.run_git("stash", "show", "-p", stash_ref, check=False)
        for pattern in patterns:
            assert pattern not in diff_result.stdout, (
                f"Secret {pattern!r} found in stash {stash_ref} diff"
            )
        # Check stash commit message
        msg_result = utils.run_git("log", "-1", "--format=%B", stash_ref, check=False)
        for pattern in patterns:
            assert pattern not in msg_result.stdout, (
                f"Secret {pattern!r} found in stash {stash_ref} message"
            )


def test_hidden_not_in_reflog() -> None:
    """No secret appears in any commit reachable via reflog."""
    patterns = utils.read_patterns()

    # Collect all reflog-reachable commits
    result = utils.run_git("reflog", "--all", "--format=%H", check=False)
    if not result.stdout.strip():
        return  # Empty reflog is fine

    seen = set()
    for line in result.stdout.strip().splitlines():
        commit_hash = line.strip()
        if not commit_hash or commit_hash in seen:
            continue
        seen.add(commit_hash)

        # Check commit message
        msg = utils.run_git("log", "-1", "--format=%B", commit_hash, check=False).stdout
        for pattern in patterns:
            assert pattern not in msg, (
                f"Secret {pattern!r} in reflog-reachable commit {commit_hash[:8]} message"
            )

        # Check commit diff
        diff = utils.run_git("diff-tree", "-p", commit_hash, check=False).stdout
        for pattern in patterns:
            assert pattern not in diff, (
                f"Secret {pattern!r} in reflog-reachable commit {commit_hash[:8]} diff"
            )


def test_hidden_not_in_orphaned_objects() -> None:
    """No secret appears in any unreachable/dangling object."""
    patterns = utils.read_patterns()

    # Find all unreachable objects
    result = utils.run_git("fsck", "--unreachable", "--no-reflogs", check=False)
    combined = result.stdout + "\n" + result.stderr

    orphan_hashes = set()
    for line in combined.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0] in ("unreachable", "dangling"):
            orphan_hashes.add(parts[2])

    for obj_hash in orphan_hashes:
        content = utils.object_content(obj_hash)
        for pattern in patterns:
            assert pattern not in content, (
                f"Secret {pattern!r} found in orphaned object {obj_hash[:8]} "
                f"(type: {utils.object_type(obj_hash)})"
            )


def test_hidden_no_base64_encoded_secret() -> None:
    """No secret appears in base64-encoded form in any blob at HEAD."""
    patterns = utils.read_patterns()

    result = utils.run_git("ls-tree", "-r", "HEAD")
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        blob_hash = parts[2]
        file_path = parts[3]
        content = utils.object_content(blob_hash)

        for text_line in content.splitlines():
            text_line = text_line.strip()
            if not text_line or text_line.startswith("#"):
                continue

            # Collect decoded candidates (outside try/except to avoid catching AssertionError)
            decoded_values: list[tuple[str, str]] = []

            # Try decoding value after = sign (key=base64value)
            if "=" in text_line:
                value = text_line.split("=", 1)[1].strip()
                if len(value) >= 4:
                    try:
                        d = base64.b64decode(value).decode("utf-8", errors="ignore")
                        decoded_values.append((value, d))
                    except Exception:
                        pass

            # Try decoding each whitespace-separated token
            for token in text_line.split():
                if len(token) >= 8:
                    try:
                        d = base64.b64decode(token).decode("utf-8", errors="ignore")
                        decoded_values.append((token, d))
                    except Exception:
                        pass

            # Now assert outside try/except
            for encoded, decoded in decoded_values:
                for pattern in patterns:
                    assert pattern not in decoded, (
                        f"Secret {pattern!r} found base64-encoded in "
                        f"{file_path} (blob {blob_hash[:8]}): "
                        f"encoded as {encoded!r}"
                    )


def test_hidden_not_split_across_lines() -> None:
    """No secret is split across adjacent lines in any blob at HEAD."""
    patterns = utils.read_patterns()

    result = utils.run_git("ls-tree", "-r", "HEAD")
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        blob_hash = parts[2]
        content = utils.object_content(blob_hash)

        # Join all lines and search for the secret
        collapsed = content.replace("\n", "")
        for pattern in patterns:
            if pattern in collapsed and "secret-patterns" not in parts[3]:
                assert False, (
                    f"Secret {pattern!r} found when joining lines in blob "
                    f"{blob_hash[:8]} ({parts[3]})"
                )


def test_hidden_not_in_replace_refs() -> None:
    """No secret appears in any replace ref or replaced object."""
    patterns = utils.read_patterns()

    result = utils.run_git("replace", "-l", check=False)
    if not result.stdout.strip():
        return  # No replace refs is fine (means they were deleted)

    for replace_hash in result.stdout.strip().splitlines():
        replace_hash = replace_hash.strip()
        if not replace_hash:
            continue

        # Check the replacement object
        ref = f"refs/replace/{replace_hash}"
        replacement_hash = utils.run_git("rev-parse", ref, check=False).stdout.strip()
        if replacement_hash:
            content = utils.object_content(replacement_hash)
            for pattern in patterns:
                assert pattern not in content, (
                    f"Secret {pattern!r} in replace ref target {replacement_hash[:8]}"
                )

            # If it's a commit, check its tree
            obj_t = utils.object_type(replacement_hash)
            if obj_t == "commit":
                tree_result = utils.run_git(
                    "ls-tree", "-r", replacement_hash, check=False
                )
                for tree_line in tree_result.stdout.strip().splitlines():
                    tparts = tree_line.split(None, 3)
                    if len(tparts) >= 3:
                        blob_content = utils.object_content(tparts[2])
                        for pattern in patterns:
                            assert pattern not in blob_content, (
                                f"Secret {pattern!r} in blob {tparts[2][:8]} "
                                f"under replace ref {replace_hash[:8]}"
                            )


def test_hidden_merge_messages_clean() -> None:
    """No secret appears in any merge commit message."""
    patterns = utils.read_patterns()

    result = utils.run_git("log", "--all", "--merges", "--format=%H %B")
    for pattern in patterns:
        assert pattern not in result.stdout, (
            f"Secret {pattern!r} found in a merge commit message"
        )


def test_hidden_hex_encoded_secret_removed() -> None:
    """No secret appears hex-encoded in any blob at HEAD."""
    patterns = utils.read_patterns()
    hex_patterns = [p.encode().hex() for p in patterns]

    result = utils.run_git("ls-tree", "-r", "HEAD")
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        blob_hash = parts[2]
        file_path = parts[3]
        content = utils.object_content(blob_hash)

        # Check for full hex-encoded secrets
        for pattern, hex_pat in zip(patterns, hex_patterns):
            assert hex_pat not in content.lower(), (
                f"Secret {pattern!r} found hex-encoded in {file_path} "
                f"(blob {blob_hash[:8]})"
            )

        # Also try decoding any hex-looking tokens in the file
        for token in re.findall(r'[0-9a-fA-F]{16,}', content):
            try:
                decoded = bytes.fromhex(token).decode("utf-8", errors="ignore")
            except (ValueError, UnicodeDecodeError):
                continue
            for pattern in patterns:
                assert pattern not in decoded, (
                    f"Secret {pattern!r} found in hex-decoded token in "
                    f"{file_path} (blob {blob_hash[:8]})"
                )


def test_hidden_custom_refs_clean() -> None:
    """No secret appears in any custom ref's tree."""
    patterns = utils.read_patterns()

    result = utils.run_git("for-each-ref", "--format=%(refname) %(objectname)",
                           "refs/custom/", check=False)
    if not result.stdout.strip():
        return  # No custom refs is fine (means they were deleted)

    for line in result.stdout.strip().splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        ref_name, obj_hash = parts[0], parts[1]

        # Check the commit object itself
        content = utils.object_content(obj_hash)
        for pattern in patterns:
            assert pattern not in content, (
                f"Secret {pattern!r} found in custom ref {ref_name} "
                f"commit object {obj_hash[:8]}"
            )

        # Check the tree
        obj_t = utils.object_type(obj_hash)
        if obj_t == "commit":
            tree_result = utils.run_git("ls-tree", "-r", obj_hash, check=False)
            for tree_line in tree_result.stdout.strip().splitlines():
                tparts = tree_line.split(None, 3)
                if len(tparts) >= 3:
                    blob_content = utils.object_content(tparts[2])
                    for pattern in patterns:
                        assert pattern not in blob_content, (
                            f"Secret {pattern!r} in blob {tparts[2][:8]} "
                            f"under custom ref {ref_name}"
                        )


def test_hidden_nested_base64_removed() -> None:
    """No secret appears in double-base64-encoded form in any blob at HEAD."""
    patterns = utils.read_patterns()

    result = utils.run_git("ls-tree", "-r", "HEAD")
    for line in result.stdout.strip().splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        blob_hash = parts[2]
        file_path = parts[3]
        content = utils.object_content(blob_hash)

        for text_line in content.splitlines():
            text_line = text_line.strip()
            if not text_line or text_line.startswith("#"):
                continue

            # Collect tokens that could be base64
            tokens = []
            if "=" in text_line:
                tokens.append(text_line.split("=", 1)[1].strip())
            tokens.extend(t for t in text_line.split() if len(t) >= 8)

            for token in tokens:
                # Try single base64 decode
                try:
                    layer1 = base64.b64decode(token).decode("utf-8", errors="ignore")
                except Exception:
                    continue

                # Try second base64 decode
                try:
                    layer2 = base64.b64decode(layer1).decode("utf-8", errors="ignore")
                except Exception:
                    continue

                for pattern in patterns:
                    assert pattern not in layer2, (
                        f"Secret {pattern!r} found double-base64-encoded in "
                        f"{file_path} (blob {blob_hash[:8]})"
                    )


def test_hidden_gitattributes_secret_removed() -> None:
    """No secret appears in .gitattributes content at HEAD."""
    patterns = utils.read_patterns()

    # Check .gitattributes at HEAD
    result = utils.run_git("show", "HEAD:.gitattributes", check=False)
    if result.returncode != 0:
        return  # No .gitattributes is fine if it was properly cleaned

    for pattern in patterns:
        assert pattern not in result.stdout, (
            f"Secret {pattern!r} found in .gitattributes at HEAD"
        )

    # Also check all historical versions of .gitattributes
    log_result = utils.run_git("log", "--all", "--format=%H", "--", ".gitattributes",
                               check=False)
    for commit_hash in log_result.stdout.strip().splitlines():
        commit_hash = commit_hash.strip()
        if not commit_hash:
            continue
        show_result = utils.run_git("show", f"{commit_hash}:.gitattributes", check=False)
        for pattern in patterns:
            assert pattern not in show_result.stdout, (
                f"Secret {pattern!r} found in .gitattributes at commit {commit_hash[:8]}"
            )


def test_hidden_fsck_no_dangling() -> None:
    """git fsck --no-reflogs reports zero dangling objects."""
    result = utils.run_git("fsck", "--no-reflogs", check=False)
    combined = result.stdout + "\n" + result.stderr

    dangling_lines = [
        line for line in combined.splitlines()
        if line.strip().startswith("dangling ")
    ]
    assert not dangling_lines, (
        f"Found {len(dangling_lines)} dangling object(s) — "
        f"model must run `git gc --prune=now` or equivalent:\n"
        + "\n".join(dangling_lines[:10])
    )


def test_hidden_decoy_preserved() -> None:
    """Decoy text in CONTRIBUTING.md must NOT be removed."""
    # The CONTRIBUTING.md contains near-miss patterns that look like secrets
    # but are legitimate documentation. Over-aggressive removal is a failure.
    result = utils.run_git("show", "HEAD:CONTRIBUTING.md", check=False)
    assert result.returncode == 0, (
        "CONTRIBUTING.md is missing from HEAD — it must be preserved"
    )

    content = result.stdout
    assert "secret[XXXX-XXXX-XXXX]" in content, (
        "Decoy pattern 'secret[XXXX-XXXX-XXXX]' was incorrectly removed "
        "from CONTRIBUTING.md — only actual secrets should be scrubbed"
    )
    assert "token-xK9p-2024-dev" in content, (
        "Decoy pattern 'token-xK9p-2024-dev' was incorrectly removed "
        "from CONTRIBUTING.md — only actual secrets should be scrubbed"
    )
