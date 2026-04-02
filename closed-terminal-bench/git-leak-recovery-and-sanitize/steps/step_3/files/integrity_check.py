from __future__ import annotations

import hashlib
import json
import pathlib
import re
import subprocess
from typing import Any

# Module-level caches — build_actual_manifest() is expensive on large repos
# (reads every file in every commit). All tests share one process, so caching
# here means the heavy scan runs once regardless of how many tests call it.
_reference_cache: dict[str, Any] | None = None
_manifest_cache: dict[str, Any] | None = None


REPO = pathlib.Path("/app/repo_large")
SECRET_FILE = pathlib.Path("/app/repo/.git/hooks/secret-patterns")
REFERENCE_FILE = pathlib.Path("/app/step_3/hidden/reference_manifest.json")
PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(<secret>|\[redacted\]|<redacted>|\[secret removed\]|<secret removed>)"
)


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True)


def run_git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(REPO), *args])


def read_secrets() -> list[str]:
    """Return all non-empty, non-whitespace lines from SECRET_FILE."""
    return [
        line
        for line in SECRET_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def find_secrets_in_blobs(secrets: list[str]) -> list[str]:
    """Scan ALL blob objects for raw secret strings. No canonicalization."""
    proc = subprocess.run(
        ["git", "-C", str(REPO),
         "cat-file", "--batch-all-objects",
         "--batch-check=%(objecttype) %(objectname)"],
        capture_output=True, text=True, check=False,
    )
    findings = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0] != "blob":
            continue
        oid = parts[1]
        try:
            content = run_git("cat-file", "-p", oid)
        except subprocess.CalledProcessError:
            continue
        for secret in secrets:
            if secret in content:
                findings.append(oid[:12])
                break
    return findings


def find_secrets_in_commit_messages(secrets: list[str]) -> list[str]:
    """Scan ALL commit messages for raw secret strings. No canonicalization."""
    FSEP = "\x1f"
    REC_END = "ENDOFCOMMITRECORD"
    result = run_git(
        "log", "--all", "--exclude=refs/notes/*",
        f"--format=%H{FSEP}%B{FSEP}{REC_END}",
    )
    findings = []
    for block in result.split(REC_END):
        block = block.strip("\n")
        if not block:
            continue
        sep = block.find(FSEP)
        if sep == -1:
            continue
        commit_hash = block[:sep].strip()
        message = block[sep + 1:]
        for secret in secrets:
            if secret in message:
                findings.append(commit_hash[:12])
                break
    return findings


def _canonicalize_text(text: str, secrets: list[str], placeholder: str) -> str:
    result = text
    for secret in secrets:
        result = result.replace(secret, "")
    result = result.replace(placeholder, "")
    return PLACEHOLDER_PATTERN.sub("", result)


def _canonical_sha256(text: str, secrets: list[str], placeholder: str) -> str:
    canonical = _canonicalize_text(text, secrets, placeholder)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _commit_message(commit: str) -> str:
    return run_git("show", "-s", "--format=%B", commit)


def _commit_metadata(commit: str) -> dict[str, str]:
    raw = run_git(
        "show",
        "-s",
        "--format=%an%x00%ae%x00%ad%x00%cn%x00%ce%x00%cd",
        commit,
    ).strip()
    parts = raw.split("\x00")
    return {
        "author_name": parts[0],
        "author_email": parts[1],
        "author_date": parts[2],
        "committer_name": parts[3],
        "committer_email": parts[4],
        "committer_date": parts[5],
    }


def load_reference() -> dict[str, Any]:
    global _reference_cache
    if _reference_cache is None:
        _reference_cache = json.loads(REFERENCE_FILE.read_text(encoding="utf-8"))
    return _reference_cache


def _bulk_commit_data(commit_oids: list[str]) -> list[dict[str, str]]:
    """Fetch parents, metadata, and message for all commits in one git log call."""
    if not commit_oids:
        return []
    # Use ASCII RS (record separator \x1e) between fields and a fixed end marker.
    # Avoid NUL bytes — they cannot be passed as subprocess args on Linux.
    FIELD_SEP = "\x1f"   # ASCII unit separator — safe in format strings
    REC_END = "ENDOFCOMMITRECORD"
    result = run_git(
        "log", "--topo-order", "--reverse",
        "--exclude=refs/notes/*", "--all",
        f"--format=%H{FIELD_SEP}%P{FIELD_SEP}%an{FIELD_SEP}%ae{FIELD_SEP}%ad"
        f"{FIELD_SEP}%cn{FIELD_SEP}%ce{FIELD_SEP}%cd{FIELD_SEP}%B{FIELD_SEP}{REC_END}",
    )
    oid_set = set(commit_oids)
    records: list[dict[str, str]] = []
    for block in result.split(REC_END):
        block = block.strip("\n")
        if not block:
            continue
        parts = block.split(FIELD_SEP, 9)
        if len(parts) < 9:
            continue
        oid = parts[0].strip()
        if oid not in oid_set:
            continue
        records.append({
            "oid": oid,
            "parents_str": parts[1].strip(),
            "author_name": parts[2],
            "author_email": parts[3],
            "author_date": parts[4],
            "committer_name": parts[5],
            "committer_email": parts[6],
            "committer_date": parts[7],
            "message": parts[8].rstrip("\n"),
        })
    return records


def build_actual_manifest() -> dict[str, Any]:
    global _manifest_cache
    if _manifest_cache is not None:
        return _manifest_cache
    secrets = read_secrets()
    reference = load_reference()
    placeholder = reference.get("secret_placeholder", "<SECRET>")

    commit_oids = run_git(
        "rev-list", "--topo-order", "--reverse",
        "--exclude=refs/notes/*", "--all",
    ).splitlines()
    commit_index = {oid: idx for idx, oid in enumerate(commit_oids)}

    # Bulk-fetch parents, metadata, and messages in a single git log call
    bulk_records = _bulk_commit_data(commit_oids)
    bulk_by_oid: dict[str, dict[str, str]] = {r["oid"]: r for r in bulk_records}

    commits: list[dict[str, Any]] = []
    for oid in commit_oids:
        rec = bulk_by_oid.get(oid, {})

        parents_str = rec.get("parents_str", "")
        parents = parents_str.split() if parents_str else []
        parent_indices = [commit_index[p] for p in parents if p]

        message = _canonicalize_text(
            rec.get("message", "").rstrip("\n"), secrets, placeholder
        )

        files: list[dict[str, str]] = []
        for path in run_git(
            "ls-tree", "-r", "--full-tree", "--name-only", oid
        ).splitlines():
            text = run_git_bytes("show", f"{oid}:{path}").decode("utf-8", "replace")
            canonical = _canonicalize_text(text, secrets, placeholder)
            # Skip files whose canonical content is only whitespace
            # (i.e. files that contained nothing but the secret).
            if not canonical.strip():
                continue
            files.append(
                {
                    "path": path,
                    "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                }
            )

        commits.append(
            {
                "parents": parent_indices,
                "author_name": rec.get("author_name", ""),
                "author_email": rec.get("author_email", ""),
                "author_date": rec.get("author_date", ""),
                "committer_name": rec.get("committer_name", ""),
                "committer_email": rec.get("committer_email", ""),
                "committer_date": rec.get("committer_date", ""),
                "message": message,
                "files": files,
            }
        )

    heads: dict[str, int] = {}
    for line in run_git(
        "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads"
    ).splitlines():
        name, oid = line.split()
        heads[name] = commit_index[oid]

    tags: list[dict[str, Any]] = []
    tag_names = run_git(
        "for-each-ref", "--format=%(refname:short)", "refs/tags"
    ).splitlines()
    for name in tag_names:
        line = run_git(
            "for-each-ref",
            "--format=%(objecttype) %(objectname) %(object)",
            f"refs/tags/{name}",
        ).strip()
        if not line:
            continue

        parts = line.split()
        object_type = parts[0]
        object_name = parts[1]
        # Lightweight tags point directly to a commit — %(object) is empty
        peeled_target = parts[2] if len(parts) >= 3 else object_name
        item: dict[str, Any] = {"name": name, "type": object_type}

        if object_type == "tag":
            item["target_commit_index"] = commit_index[peeled_target]
            tag_text = run_git_bytes("cat-file", "-p", object_name).decode(
                "utf-8", "replace"
            )
            message = tag_text.split("\n\n", 1)[1] if "\n\n" in tag_text else ""
            item["message"] = _canonicalize_text(
                message.rstrip("\n"), secrets, placeholder
            )
        else:
            item["target_commit_index"] = commit_index[object_name]

        tags.append(item)

    tags.sort(key=lambda x: x["name"])

    _manifest_cache = {
        "expected_refs": {
            "heads": heads,
            "tags": tags,
        },
        "commits": commits,
    }
    return _manifest_cache
