from __future__ import annotations

import pathlib
import subprocess


REPO = pathlib.Path("/app/repo")
SECRET_FILE = pathlib.Path("/app/repo/.git/hooks/secret-patterns")


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def read_secrets() -> list[str]:
    """Return all non-empty, non-whitespace lines from SECRET_FILE."""
    return [
        line
        for line in SECRET_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_secret() -> str:
    """Return the first secret from SECRET_FILE (backward compatibility)."""
    return read_secrets()[0]


def find_secret_in_tracked_blobs_multi(secrets: list[str]) -> list[dict[str, str]]:
    """Scan all tracked blobs using git cat-file --batch (one subprocess per scan, not one per blob)."""
    import subprocess as _sp

    # 1. Get all objects with paths in one call
    rev_result = run_git("rev-list", "--objects", "--all")
    oid_path_pairs: list[tuple[str, str]] = []
    for line in rev_result.stdout.splitlines():
        if " " in line:
            oid, path = line.split(" ", 1)
            oid_path_pairs.append((oid, path))
    if not oid_path_pairs:
        return []

    # 2. Filter to blobs only via --batch-check (one call)
    oids = [p[0] for p in oid_path_pairs]
    path_by_oid = {p[0]: p[1] for p in oid_path_pairs}
    check = _sp.run(
        ["git", "-C", str(REPO), "cat-file", "--batch-check=%(objectname) %(objecttype)"],
        input="\n".join(oids).encode(), capture_output=True,
    )
    blob_oids: list[str] = []
    seen: set[str] = set()
    for line in check.stdout.decode().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "blob" and parts[0] not in seen:
            blob_oids.append(parts[0])
            seen.add(parts[0])
    if not blob_oids:
        return []

    # 3. Read all blob contents in one --batch call
    batch = _sp.run(
        ["git", "-C", str(REPO), "cat-file", "--batch"],
        input="\n".join(blob_oids).encode(), capture_output=True,
    )
    data = batch.stdout
    findings: list[dict[str, str]] = []
    pos = 0
    for oid in blob_oids:
        nl = data.find(b"\n", pos)
        if nl == -1:
            break
        header = data[pos:nl].decode("ascii", "replace")
        hparts = header.split()
        if len(hparts) < 3:
            pos = nl + 1
            continue
        size = int(hparts[2])
        content = data[nl + 1: nl + 1 + size].decode("utf-8", "replace")
        for secret in secrets:
            if secret in content:
                findings.append({"object": oid, "path": path_by_oid.get(oid, ""), "secret": secret})
                break  # one finding per blob is enough
        pos = nl + 1 + size + 1  # +1 for trailing newline after content
    return findings


def find_secret_in_tracked_blobs(secret: str) -> list[dict[str, str]]:
    return find_secret_in_tracked_blobs_multi([secret])


def find_secret_in_commit_messages_multi(secrets: list[str]) -> list[dict[str, str]]:
    """Scan all commit messages in a single git log call."""
    # Avoid NUL bytes — they cannot be passed as subprocess args on Linux.
    FIELD_SEP = "\x1f"
    REC_END = "ENDCOMMIT"
    result = run_git("log", "--all", f"--format=%H{FIELD_SEP}%B{FIELD_SEP}{REC_END}")
    findings: list[dict[str, str]] = []
    for block in result.stdout.split(REC_END):
        block = block.strip("\n")
        if not block:
            continue
        sep = block.find(FIELD_SEP)
        if sep == -1:
            continue
        commit_hash = block[:sep].strip()
        message = block[sep + 1:].rsplit(FIELD_SEP, 1)[0]
        for secret in secrets:
            if secret in message:
                findings.append({"commit": commit_hash, "secret": secret})
    return findings


def find_secret_in_commit_messages(secret: str) -> list[dict[str, str]]:
    return find_secret_in_commit_messages_multi([secret])


def find_secret_in_tags_multi(secrets: list[str]) -> list[dict[str, str]]:
    lines = run_git(
        "for-each-ref",
        "--format=%(refname)%00%(objecttype)%00%(objectname)%00%(contents)",
        "refs/tags",
    ).stdout.splitlines()

    findings: list[dict[str, str]] = []
    for line in lines:
        fields = line.split("\x00")
        refname = fields[0] if len(fields) > 0 else ""
        object_type = fields[1] if len(fields) > 1 else ""
        object_name = fields[2] if len(fields) > 2 else ""
        contents = fields[3] if len(fields) > 3 else ""

        for secret in secrets:
            if secret in refname:
                findings.append({"ref": refname, "field": "refname", "secret": secret})
            if secret in contents:
                findings.append({"ref": refname, "field": "contents", "secret": secret})

        if object_type == "tag":
            tag_object = run_git("cat-file", "-p", object_name).stdout
            for secret in secrets:
                if secret in tag_object:
                    findings.append({"ref": refname, "field": "tag-object", "secret": secret})

    return findings


def find_secret_in_tags(secret: str) -> list[dict[str, str]]:
    return find_secret_in_tags_multi([secret])


def find_secret_in_notes(secrets: list[str]) -> list[dict]:
    # git notes list gives: <note_blob> <annotated_object>
    result = run_git("notes", "list", check=False)
    findings = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        note_blob, target = parts[0], parts[1]
        note_content = run_git("cat-file", "-p", note_blob, check=False).stdout
        for secret in secrets:
            if secret in note_content:
                findings.append({"note_target": target, "secret": secret})
    return findings


def get_all_commit_metadata() -> list[dict[str, str]]:
    """Return metadata for all commits in chronological order (oldest first).

    Uses a single git log call.  Each dict has keys: hash, author_name,
    author_email, author_date, committer_name, committer_email,
    committer_date, message.
    """
    FIELD_SEP = "\x1f"
    REC_END = "ENDOFCOMMITRECORD"
    result = run_git(
        "log", "--topo-order", "--reverse",
        "--exclude=refs/notes/*", "--all",
        f"--format=%H{FIELD_SEP}%an{FIELD_SEP}%ae{FIELD_SEP}%ad{FIELD_SEP}"
        f"%cn{FIELD_SEP}%ce{FIELD_SEP}%cd{FIELD_SEP}%B{FIELD_SEP}{REC_END}",
    )
    commits: list[dict[str, str]] = []
    for block in result.stdout.split(REC_END):
        block = block.strip("\n")
        if not block:
            continue
        parts = block.split(FIELD_SEP, 8)
        if len(parts) < 8:
            continue
        commits.append({
            "hash": parts[0].strip(),
            "author_name": parts[1],
            "author_email": parts[2],
            "author_date": parts[3],
            "committer_name": parts[4],
            "committer_email": parts[5],
            "committer_date": parts[6],
            "message": parts[7].rstrip("\n"),
        })
    return commits


def ensure_repo_clean() -> None:
    status = run_git("status", "--porcelain").stdout.strip()
    if status:
        raise AssertionError(f"repo is not clean:\n{status}")
