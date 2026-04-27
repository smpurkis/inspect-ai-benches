#!/usr/bin/env python3
"""
Build a git repo with secrets buried in 14 unusual locations.
Outputs environment/repo.tgz for the git-hooks forensics benchmark.

Secret hiding places:
  1. Normal file history (added then removed)
  2. Commit message containing secret
  3. Annotated tag message
  4. Git notes on a commit
  5. Stash entry
  6. Orphaned branch (deleted, reachable only via reflog/objects)
  7. Base64-encoded in a config file at HEAD
  8. Secret split across two adjacent lines in a blob
  9. Merge commit message
 10. Replace ref (git replace)
 11. Hex-encoded secret in a config file
 12. Custom ref namespace (refs/custom/leaked)
 13. Nested double-base64 encoded secret
 14. Secret embedded in .gitattributes filter spec

Decoy: A near-miss pattern in CONTRIBUTING.md that must be preserved.
"""

import base64
import os
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

SECRET1 = "secret[A7K3-LEAK-9910]"
SECRET2 = "token-xK9p-2024-prod"

ALICE = ("Alice Developer", "alice@dev.example.com")
BOB = ("Bob Smith", "bob@dev.example.com")

NUM_COMMITS = 60
START_DATE = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2025, 12, 31, 18, 0, 0, tzinfo=timezone.utc)

interval = (END_DATE - START_DATE).total_seconds() / (NUM_COMMITS - 1)

BOB_INDICES = {3, 8, 12, 15, 19, 22, 27, 31, 36, 39, 43, 46, 48, 55, 58}

# Key indices for secret planting
SECRET_FILE_ADD = 10
SECRET_FILE_REMOVE = 15
SECRET_COMMIT_MSG = 20
TAG_INDEX = 35
NOTE_INDEX = 30
MERGE_BASE = 40
MERGE_INDEX = 45
SPLIT_SECRET_INDEX = 50
REPLACE_TARGET = 5
HEX_SECRET_INDEX = 25
NESTED_B64_INDEX = 52
GITATTRIBUTES_INDEX = 54
DECOY_INDEX = 28


def run(cmd, cwd=None, env=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command {cmd} failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
    return result.stdout.strip()


def make_date(index):
    dt = START_DATE + timedelta(seconds=interval * index)
    return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")


def make_env(author, committer, date_str, base_env):
    env = base_env.copy()
    env["GIT_AUTHOR_NAME"] = author[0]
    env["GIT_AUTHOR_EMAIL"] = author[1]
    env["GIT_AUTHOR_DATE"] = date_str
    env["GIT_COMMITTER_NAME"] = committer[0]
    env["GIT_COMMITTER_EMAIL"] = committer[1]
    env["GIT_COMMITTER_DATE"] = date_str
    return env


def write_file(repo_dir, path, content):
    full = Path(repo_dir) / path
    full.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        full.write_bytes(content)
    else:
        full.write_text(content)


def create_repo():
    repo_dir = tempfile.mkdtemp(prefix="repo_forensics_")
    print(f"Creating repo at: {repo_dir}")

    base_env = os.environ.copy()
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"
    base_env["HOME"] = repo_dir

    run(["git", "init", "-b", "main"], cwd=repo_dir, env=base_env)
    run(["git", "config", "user.name", ALICE[0]], cwd=repo_dir, env=base_env)
    run(["git", "config", "user.email", ALICE[1]], cwd=repo_dir, env=base_env)

    files = {
        "README.md": "# Acme Project\n\nInternal tooling for the Acme platform.\n",
        "src/app.py": "#!/usr/bin/env python3\n\ndef main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n",
        "src/utils.py": "def helper():\n    pass\n",
        "src/config.py": "import os\n\nDEBUG = os.getenv('DEBUG', 'false').lower() == 'true'\n",
        "config/settings.cfg": "[general]\ndebug = false\nlog_level = INFO\n",
        "config/api.cfg": "[api]\nbase_url = https://api.example.com\n",
        "tests/test_app.py": "import pytest\n\ndef test_placeholder():\n    assert True\n",
        "docs/changelog.md": "# Changelog\n\n## Unreleased\n- Initial setup\n",
    }

    for path, content in files.items():
        write_file(repo_dir, path, content)

    write_file(repo_dir, "secret-patterns.txt", f"{SECRET1}\n{SECRET2}\n")

    commit_hashes = []

    for i in range(NUM_COMMITS):
        date_str = make_date(i)
        author = BOB if i in BOB_INDICES else ALICE
        env = make_env(author, author, date_str, base_env)

        if i == 0:
            run(["git", "add", "-A"], cwd=repo_dir, env=env)
            msg = "Initial project setup"

        elif i == SECRET_FILE_ADD:
            api_cfg = (Path(repo_dir) / "config/api.cfg").read_text()
            api_cfg += f"\napi_key = {SECRET1}\n"
            write_file(repo_dir, "config/api.cfg", api_cfg)
            run(["git", "add", "config/api.cfg"], cwd=repo_dir, env=env)
            msg = "Add staging API configuration"

        elif i == SECRET_FILE_REMOVE:
            write_file(repo_dir, "config/api.cfg",
                       "[api]\nbase_url = https://api.example.com\napi_key = <PLACEHOLDER>\n")
            run(["git", "add", "config/api.cfg"], cwd=repo_dir, env=env)
            msg = "Remove hardcoded API key"

        elif i == SECRET_COMMIT_MSG:
            content = (Path(repo_dir) / "src/app.py").read_text()
            content += "\n# Security patch applied\n"
            write_file(repo_dir, "src/app.py", content)
            run(["git", "add", "src/app.py"], cwd=repo_dir, env=env)
            msg = f"Rotate credentials — old key was {SECRET2}, now using vault"

        elif i == SPLIT_SECRET_INDEX:
            mid = len(SECRET1) // 2
            # Secret split literally across a line boundary
            split_content = (
                f"# Long token value (auto-wrapped):\n"
                f"legacy_token = {SECRET1[:mid]}\n"
                f"{SECRET1[mid:]}\n"
                f"# end of legacy config\n"
            )
            write_file(repo_dir, "config/fragments.cfg", split_content)
            run(["git", "add", "config/fragments.cfg"], cwd=repo_dir, env=env)
            msg = "Add configuration fragments"

        elif i == HEX_SECRET_INDEX:
            # --- HIDING PLACE 11: hex-encoded secret ---
            hex_encoded = SECRET1.encode().hex()
            hex_content = (
                "# Hardware token identifiers (hex-encoded)\n"
                f"primary_token = {hex_encoded}\n"
                "backup_token = 6e6f742d612d7265616c2d746f6b656e\n"
            )
            write_file(repo_dir, "config/tokens.hex", hex_content)
            run(["git", "add", "config/tokens.hex"], cwd=repo_dir, env=env)
            msg = "Add hardware token identifiers"

        elif i == DECOY_INDEX:
            # --- DECOY: near-miss pattern that must be preserved ---
            decoy_content = (
                "# Contributing to Acme Project\n\n"
                "## Security\n\n"
                "Do not use patterns like secret[XXXX-XXXX-XXXX] in code.\n"
                "Previous token format: token-xK9p-2024-dev (deprecated).\n"
                "Always use vault references instead of hardcoded credentials.\n"
            )
            write_file(repo_dir, "CONTRIBUTING.md", decoy_content)
            run(["git", "add", "CONTRIBUTING.md"], cwd=repo_dir, env=env)
            msg = "Add contributing guidelines"

        elif i == NESTED_B64_INDEX:
            # --- HIDING PLACE 13: nested double-base64 ---
            inner_b64 = base64.b64encode(SECRET1.encode()).decode()
            outer_b64 = base64.b64encode(inner_b64.encode()).decode()
            auth_content = (
                "# Auth token cache (base64-wrapped)\n"
                f"refresh_token = {outer_b64}\n"
                "# Rotate quarterly\n"
            )
            write_file(repo_dir, "config/auth.b64", auth_content)
            run(["git", "add", "config/auth.b64"], cwd=repo_dir, env=env)
            msg = "Add auth token cache"

        elif i == GITATTRIBUTES_INDEX:
            # --- HIDING PLACE 14: secret in .gitattributes filter spec ---
            gitattr_content = (
                "*.py text eol=lf\n"
                "*.cfg text eol=lf\n"
                f"*.dat filter=clean-{SECRET2}\n"
                "*.bin binary\n"
            )
            write_file(repo_dir, ".gitattributes", gitattr_content)
            run(["git", "add", ".gitattributes"], cwd=repo_dir, env=env)
            msg = "Add gitattributes for consistent line endings"

        elif i == NUM_COMMITS - 2:
            b64 = base64.b64encode(SECRET2.encode()).decode()
            env_content = (
                f"# Encrypted environment tokens\n"
                f"DB_HOST=db.internal.example.com\n"
                f"DB_PORT=5432\n"
                f"API_TOKEN_ENC={b64}\n"
                f"LOG_LEVEL=info\n"
            )
            write_file(repo_dir, ".env.enc", env_content)
            run(["git", "add", ".env.enc"], cwd=repo_dir, env=env)
            msg = "Add encrypted environment configuration"

        else:
            cycle = i % 8
            target_files = [
                "src/app.py", "src/utils.py", "docs/changelog.md",
                "tests/test_app.py", "config/settings.cfg", "src/config.py",
                "README.md", "src/utils.py",
            ]
            f = target_files[cycle]
            content = (Path(repo_dir) / f).read_text()
            content += f"\n# Update {i}\n"
            write_file(repo_dir, f, content)
            run(["git", "add", f], cwd=repo_dir, env=env)
            msg = f"Commit {i}: routine update"

        run(["git", "commit", "-m", msg], cwd=repo_dir, env=env)
        h = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
        commit_hashes.append(h)
        print(f"  [{i:02d}] {h[:8]} {msg[:60]}")

    # --- HIDING PLACE 3: annotated tag with secret in message ---
    tag_hash = commit_hashes[TAG_INDEX]
    tag_env = make_env(ALICE, ALICE, make_date(TAG_INDEX), base_env)
    run(["git", "tag", "-a", "v1.0", tag_hash,
         "-m", f"Release v1.0\n\nStaging credential for rollback: {SECRET1}"],
        cwd=repo_dir, env=tag_env)
    print(f"\n  Tag v1.0 at [{TAG_INDEX}] ({tag_hash[:8]}) — secret in annotation")

    # --- HIDING PLACE 4: git note with secret ---
    note_hash = commit_hashes[NOTE_INDEX]
    note_env = make_env(ALICE, ALICE, make_date(NOTE_INDEX), base_env)
    run(["git", "notes", "add", "-m",
         f"Security review: {SECRET2} was active during this period.",
         note_hash], cwd=repo_dir, env=note_env)
    print(f"  Note on [{NOTE_INDEX}] ({note_hash[:8]}) — secret in note")

    # --- HIDING PLACE 5: stash entry with secret ---
    write_file(repo_dir, "tmp_debug.txt",
               f"Debug dump:\nAPI key in use: {SECRET1}\nEnd of dump.\n")
    run(["git", "add", "tmp_debug.txt"], cwd=repo_dir, env=base_env)
    stash_env = make_env(ALICE, ALICE, make_date(NUM_COMMITS - 1), base_env)
    run(["git", "stash", "push", "-m", "WIP: debug session"],
        cwd=repo_dir, env=stash_env)
    print(f"  Stash created with secret in tmp_debug.txt")

    # --- HIDING PLACE 6: orphaned branch ---
    orphan_env = make_env(BOB, BOB, make_date(NUM_COMMITS - 1), base_env)
    run(["git", "checkout", "-b", "temp/debug-leak"], cwd=repo_dir, env=base_env)
    write_file(repo_dir, "debug_credentials.txt",
               f"=== Debug Credentials ===\nPROD_TOKEN={SECRET2}\nSTAGING_KEY={SECRET1}\n")
    run(["git", "add", "debug_credentials.txt"], cwd=repo_dir, env=orphan_env)
    run(["git", "commit", "-m", "WIP: debug credentials for testing"],
        cwd=repo_dir, env=orphan_env)
    orphan_hash = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
    print(f"  Orphan branch commit: {orphan_hash[:8]}")
    run(["git", "checkout", "main"], cwd=repo_dir, env=base_env)
    run(["git", "branch", "-D", "temp/debug-leak"], cwd=repo_dir, env=base_env)
    print(f"  Branch temp/debug-leak deleted (commit orphaned)")

    # --- HIDING PLACE 9: merge commit with secret in message ---
    merge_base_hash = commit_hashes[MERGE_BASE]
    merge_env = make_env(ALICE, ALICE, make_date(MERGE_INDEX), base_env)
    run(["git", "checkout", "-b", "feature/auth-update", merge_base_hash],
        cwd=repo_dir, env=base_env)
    write_file(repo_dir, "src/auth.py",
               "# Authentication module\ndef authenticate(user):\n    pass\n")
    run(["git", "add", "src/auth.py"], cwd=repo_dir, env=merge_env)
    run(["git", "commit", "-m", "Add auth module"], cwd=repo_dir, env=merge_env)
    run(["git", "checkout", "main"], cwd=repo_dir, env=base_env)
    run(["git", "merge", "--no-ff", "feature/auth-update",
         "-m", f"Merge feature/auth-update — verified with {SECRET1}"],
        cwd=repo_dir, env=merge_env)
    run(["git", "branch", "-d", "feature/auth-update"], cwd=repo_dir, env=base_env)
    merge_hash = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
    print(f"  Merge commit: {merge_hash[:8]} — secret in merge message")

    final_count = run(["git", "rev-list", "--count", "HEAD"], cwd=repo_dir, env=base_env)
    print(f"  Final commit count on main: {final_count}")

    # --- HIDING PLACE 10: replace ref ---
    replace_target_hash = commit_hashes[REPLACE_TARGET]
    run(["git", "checkout", "--detach", replace_target_hash], cwd=repo_dir, env=base_env)
    write_file(repo_dir, ".internal/credentials.bak", f"backup: {SECRET2}\n")
    run(["git", "add", ".internal/credentials.bak"], cwd=repo_dir, env=base_env)
    replace_env = make_env(ALICE, ALICE, make_date(REPLACE_TARGET), base_env)
    run(["git", "commit", "--amend", "--no-edit"], cwd=repo_dir, env=replace_env)
    replace_new_hash = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
    run(["git", "replace", replace_target_hash, replace_new_hash],
        cwd=repo_dir, env=base_env)
    run(["git", "checkout", "main"], cwd=repo_dir, env=base_env)
    print(f"  Replace ref: {replace_target_hash[:8]} → {replace_new_hash[:8]}")

    # --- HIDING PLACE 12: custom ref namespace ---
    # Create a detached commit with SECRET2 in a file, then point a custom ref at it.
    # Custom refs under refs/custom/ are invisible to `git log --all`.
    custom_env = make_env(BOB, BOB, make_date(NUM_COMMITS - 1), base_env)
    run(["git", "checkout", "--orphan", "tmp-custom-ref"], cwd=repo_dir, env=base_env)
    run(["git", "rm", "-rf", "."], cwd=repo_dir, env=base_env)
    write_file(repo_dir, "leaked_config.ini",
               f"[credentials]\nservice_token = {SECRET2}\n")
    run(["git", "add", "leaked_config.ini"], cwd=repo_dir, env=custom_env)
    run(["git", "commit", "-m", "internal: credential snapshot"],
        cwd=repo_dir, env=custom_env)
    custom_hash = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
    run(["git", "update-ref", "refs/custom/leaked", custom_hash],
        cwd=repo_dir, env=base_env)
    run(["git", "checkout", "main"], cwd=repo_dir, env=base_env)
    run(["git", "branch", "-D", "tmp-custom-ref"], cwd=repo_dir, env=base_env)
    print(f"  Custom ref refs/custom/leaked at {custom_hash[:8]} — secret in tree")

    # Clean working tree
    internal_path = Path(repo_dir) / ".internal"
    if internal_path.exists():
        shutil.rmtree(internal_path)

    return repo_dir, commit_hashes, orphan_hash, int(final_count)


def verify(repo_dir, commit_hashes, orphan_hash, final_count):
    print("\n--- Verification ---")
    base_env = os.environ.copy()
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"
    base_env["HOME"] = repo_dir

    # 1. SECRET1 in file history
    out = run(["git", "log", "-p", "--all", "-S", SECRET1], cwd=repo_dir, env=base_env)
    assert SECRET1 in out, "FAIL: SECRET1 not in file history"
    print("  [1] Secret in file history: OK")

    # 2. SECRET2 in commit message
    out = run(["git", "log", "--all", "--format=%B"], cwd=repo_dir, env=base_env)
    assert SECRET2 in out, "FAIL: SECRET2 not in commit messages"
    print("  [2] Secret in commit message: OK")

    # 3. SECRET1 in tag message
    out = run(["git", "cat-file", "-p", "v1.0"], cwd=repo_dir, env=base_env)
    assert SECRET1 in out, "FAIL: SECRET1 not in tag message"
    print("  [3] Secret in tag message: OK")

    # 4. SECRET2 in git notes
    note_hash = commit_hashes[NOTE_INDEX]
    out = run(["git", "notes", "show", note_hash], cwd=repo_dir, env=base_env)
    assert SECRET2 in out, "FAIL: SECRET2 not in git notes"
    print("  [4] Secret in git notes: OK")

    # 5. SECRET1 in stash
    out = run(["git", "stash", "show", "-p", "stash@{0}"], cwd=repo_dir, env=base_env)
    assert SECRET1 in out, "FAIL: SECRET1 not in stash"
    print("  [5] Secret in stash: OK")

    # 6. Orphaned commit
    out = run(["git", "cat-file", "-p", orphan_hash], cwd=repo_dir, env=base_env)
    tree_hash = [l.split()[1] for l in out.split("\n") if l.startswith("tree")][0]
    tree_out = run(["git", "ls-tree", "-r", tree_hash], cwd=repo_dir, env=base_env)
    found = False
    for line in tree_out.split("\n"):
        if "debug_credentials" in line:
            blob_hash = line.split()[2]
            blob = run(["git", "cat-file", "-p", blob_hash], cwd=repo_dir, env=base_env)
            assert SECRET2 in blob
            found = True
    assert found, "FAIL: SECRET2 not in orphaned commit"
    print("  [6] Secret in orphaned commit: OK")

    # 7. Base64 at HEAD
    env_content = (Path(repo_dir) / ".env.enc").read_text()
    for line in env_content.split("\n"):
        if "API_TOKEN_ENC=" in line:
            encoded = line.split("=", 1)[1]
            decoded = base64.b64decode(encoded).decode()
            assert SECRET2 in decoded
    print("  [7] Base64-encoded secret: OK")

    # 8. Split across lines — secret spans a line boundary
    content = (Path(repo_dir) / "config/fragments.cfg").read_text()
    collapsed = content.replace("\n", "")
    assert SECRET1 in collapsed, "FAIL: secret not recoverable by joining lines"
    # But NOT on a single line
    assert not any(SECRET1 in line for line in content.splitlines()), \
        "FAIL: secret should span lines, not be on one line"
    print("  [8] Split-across-lines secret: OK")

    # 9. Merge message
    out = run(["git", "log", "--merges", "--format=%B"], cwd=repo_dir, env=base_env)
    assert SECRET1 in out, "FAIL: SECRET1 not in merge message"
    print("  [9] Secret in merge message: OK")

    # 10. Replace ref
    out = run(["git", "replace", "-l"], cwd=repo_dir, env=base_env)
    assert out.strip(), "FAIL: no replace refs"
    print(" [10] Replace ref exists: OK")

    # 11. Hex-encoded secret at HEAD
    hex_content = (Path(repo_dir) / "config/tokens.hex").read_text()
    hex_encoded = SECRET1.encode().hex()
    assert hex_encoded in hex_content, "FAIL: hex-encoded SECRET1 not in tokens.hex"
    decoded = bytes.fromhex(hex_encoded).decode()
    assert decoded == SECRET1
    print(" [11] Hex-encoded secret: OK")

    # 12. Custom ref namespace
    out = run(["git", "for-each-ref", "refs/custom/"], cwd=repo_dir, env=base_env)
    assert "refs/custom/leaked" in out, "FAIL: custom ref not found"
    custom_hash = run(["git", "rev-parse", "refs/custom/leaked"], cwd=repo_dir, env=base_env)
    tree_out = run(["git", "ls-tree", "-r", custom_hash], cwd=repo_dir, env=base_env)
    for tline in tree_out.split("\n"):
        if "leaked_config" in tline:
            blob_h = tline.split()[2]
            blob_c = run(["git", "cat-file", "-p", blob_h], cwd=repo_dir, env=base_env)
            assert SECRET2 in blob_c, "FAIL: SECRET2 not in custom ref blob"
    print(" [12] Custom ref namespace: OK")

    # 13. Nested base64 at HEAD
    auth_content = (Path(repo_dir) / "config/auth.b64").read_text()
    for line in auth_content.split("\n"):
        if "refresh_token" in line:
            token = line.split("=", 1)[1].strip()
            inner = base64.b64decode(token).decode()
            decoded = base64.b64decode(inner).decode()
            assert decoded == SECRET1, "FAIL: nested base64 doesn't decode to SECRET1"
    print(" [13] Nested base64 secret: OK")

    # 14. Secret in .gitattributes
    gitattr = (Path(repo_dir) / ".gitattributes").read_text()
    assert SECRET2 in gitattr, "FAIL: SECRET2 not in .gitattributes"
    print(" [14] Secret in .gitattributes: OK")

    # Decoy preserved
    contrib = (Path(repo_dir) / "CONTRIBUTING.md").read_text()
    assert "secret[XXXX-XXXX-XXXX]" in contrib, "FAIL: decoy pattern missing"
    assert "token-xK9p-2024-dev" in contrib, "FAIL: decoy near-miss missing"
    print(" [--] Decoy text in CONTRIBUTING.md: OK")

    print(f"\nAll 14 hiding places + decoy verified. Commit count: {final_count}")


def package(repo_dir, output_path):
    print(f"\nPackaging repo to: {output_path}")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(repo_dir, arcname=".")
    size = os.path.getsize(output_path)
    print(f"Archive size: {size:,} bytes ({size / 1024:.1f} KB)")


def main():
    repo_dir, commit_hashes, orphan_hash, final_count = create_repo()
    verify(repo_dir, commit_hashes, orphan_hash, final_count)
    output_path = SCRIPT_DIR / "repo.tgz"
    package(repo_dir, str(output_path))
    shutil.rmtree(repo_dir)
    print(f"\nDone. repo.tgz created at: {output_path}")


if __name__ == "__main__":
    main()
