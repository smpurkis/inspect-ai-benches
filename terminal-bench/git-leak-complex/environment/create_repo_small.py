#!/usr/bin/env python3
"""
Create a 50-commit linear git repo for the git-leak-recovery-and-sanitize benchmark.
Packages result as environment/repo_small.tgz.
"""

import os
import subprocess
import tempfile
import tarfile
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

SECRET1 = "secret[A7K3-LEAK-9910]"
SECRET2 = "token-xK9p-2024-prod"

ALICE = ("Alice Developer", "alice@dev.example.com")
BOB = ("Bob Smith", "bob@dev.example.com")
AGENT = ("Agent", "agent@example.com")

NUM_COMMITS = 50
START_DATE = datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2025, 12, 31, 18, 0, 0, tzinfo=timezone.utc)

# Spread commits evenly
total_seconds = (END_DATE - START_DATE).total_seconds()
interval = total_seconds / (NUM_COMMITS - 1)

# Author assignment: 70% Alice (35 commits), 30% Bob (15 commits)
# Indices where Bob authors (spread across the 50 commits)
BOB_INDICES = {3, 8, 12, 15, 19, 22, 27, 31, 36, 39, 43, 46, 48, 49, 14}

# Indices where author=Alice but committer=Agent (~5 commits)
AGENT_COMMITTER_INDICES = {5, 17, 25, 33, 41}

# Special commits
SECRET1_ADD_INDEX = 15   # ~2025-04-01
SECRET1_REMOVE_INDEX = 20  # ~2025-05-15
TAG_INDEX = 35           # ~2025-09-01
NOTE_INDEX = 30          # add git note here


def run(cmd, cwd=None, env=None):
    result = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command {cmd} failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
    return result.stdout.strip()


def make_date(index):
    dt = START_DATE + timedelta(seconds=interval * index)
    # Format: "2025-01-01T10:00:00+0000"
    return dt.strftime("%Y-%m-%dT%H:%M:%S+0000")


def make_env(author_name, author_email, committer_name, committer_email, date_str, base_env):
    env = base_env.copy()
    env["GIT_AUTHOR_NAME"] = author_name
    env["GIT_AUTHOR_EMAIL"] = author_email
    env["GIT_AUTHOR_DATE"] = date_str
    env["GIT_COMMITTER_NAME"] = committer_name
    env["GIT_COMMITTER_EMAIL"] = committer_email
    env["GIT_COMMITTER_DATE"] = date_str
    return env


def create_repo():
    repo_dir = tempfile.mkdtemp(prefix="repo_small_")
    print(f"Creating repo at: {repo_dir}")

    base_env = os.environ.copy()
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"
    base_env["HOME"] = repo_dir  # avoid picking up user git config

    run(["git", "init", "-b", "main"], cwd=repo_dir, env=base_env)
    run(["git", "config", "user.name", "Alice Developer"], cwd=repo_dir, env=base_env)
    run(["git", "config", "user.email", "alice@dev.example.com"], cwd=repo_dir, env=base_env)

    # Create initial file structure
    (Path(repo_dir) / "src").mkdir()
    (Path(repo_dir) / "config").mkdir()
    (Path(repo_dir) / "tests").mkdir()
    (Path(repo_dir) / "docs").mkdir()

    # Initial file contents
    files = {
        "README.md": "# Project\n\nA sample project for benchmarking.\n",
        "src/app.py": "#!/usr/bin/env python3\n\ndef main():\n    print('Hello, World!')\n\nif __name__ == '__main__':\n    main()\n",
        "src/utils.py": "def helper():\n    pass\n",
        "src/config.py": "import os\n\nDEBUG = os.getenv('DEBUG', 'false').lower() == 'true'\n",
        "config/settings.cfg": "[general]\ndebug = false\nlog_level = INFO\n",
        "config/api.cfg": "[api]\nbase_url = https://api.example.com\n",
        "tests/test_app.py": "import pytest\n\ndef test_placeholder():\n    assert True\n",
        "docs/changelog.md": "# Changelog\n\n## Unreleased\n- Initial setup\n",
    }

    def write_file(path, content):
        full = Path(repo_dir) / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    for path, content in files.items():
        write_file(path, content)

    commit_hashes = []

    for i in range(NUM_COMMITS):
        date_str = make_date(i)

        # Determine author
        if i in BOB_INDICES:
            author = BOB
        else:
            author = ALICE

        # Determine committer
        if i in AGENT_COMMITTER_INDICES:
            committer = AGENT
        else:
            committer = author

        env = make_env(
            author[0], author[1],
            committer[0], committer[1],
            date_str,
            base_env,
        )

        # Modify files based on commit index
        if i == 0:
            # Initial commit — already staged above
            run(["git", "add", "-A"], cwd=repo_dir, env=env)
            msg = "Initial project setup"

        elif i == SECRET1_ADD_INDEX:
            # Add secret to config/api.cfg
            api_cfg = (Path(repo_dir) / "config/api.cfg").read_text()
            api_cfg += f"\napi_key = {SECRET1}\n"
            write_file("config/api.cfg", api_cfg)
            run(["git", "add", "config/api.cfg"], cwd=repo_dir, env=env)
            msg = f"Add staging API config with key {SECRET1}"

        elif i == SECRET1_REMOVE_INDEX:
            # Remove secret from config/api.cfg
            write_file("config/api.cfg", "[api]\nbase_url = https://api.example.com\napi_key = <PLACEHOLDER>\n")
            run(["git", "add", "config/api.cfg"], cwd=repo_dir, env=env)
            msg = "Remove hardcoded API key"

        else:
            # Generic commit — rotate through meaningful changes
            cycle = i % 8
            if cycle == 0:
                content = (Path(repo_dir) / "src/app.py").read_text()
                content += f"\n# Update {i}\n"
                write_file("src/app.py", content)
                run(["git", "add", "src/app.py"], cwd=repo_dir, env=env)
            elif cycle == 1:
                content = (Path(repo_dir) / "src/utils.py").read_text()
                content += f"\n# Utility update {i}\n"
                write_file("src/utils.py", content)
                run(["git", "add", "src/utils.py"], cwd=repo_dir, env=env)
            elif cycle == 2:
                content = (Path(repo_dir) / "docs/changelog.md").read_text()
                content += f"\n- Commit {i} changes\n"
                write_file("docs/changelog.md", content)
                run(["git", "add", "docs/changelog.md"], cwd=repo_dir, env=env)
            elif cycle == 3:
                content = (Path(repo_dir) / "tests/test_app.py").read_text()
                content += f"\ndef test_case_{i}():\n    assert True\n"
                write_file("tests/test_app.py", content)
                run(["git", "add", "tests/test_app.py"], cwd=repo_dir, env=env)
            elif cycle == 4:
                content = (Path(repo_dir) / "config/settings.cfg").read_text()
                content += f"\n# Setting updated at commit {i}\n"
                write_file("config/settings.cfg", content)
                run(["git", "add", "config/settings.cfg"], cwd=repo_dir, env=env)
            elif cycle == 5:
                content = (Path(repo_dir) / "src/config.py").read_text()
                content += f"\n# Config tweak {i}\n"
                write_file("src/config.py", content)
                run(["git", "add", "src/config.py"], cwd=repo_dir, env=env)
            elif cycle == 6:
                content = (Path(repo_dir) / "README.md").read_text()
                content += f"\n<!-- update {i} -->\n"
                write_file("README.md", content)
                run(["git", "add", "README.md"], cwd=repo_dir, env=env)
            else:
                content = (Path(repo_dir) / "src/utils.py").read_text()
                content += f"\n# Helper revision {i}\n"
                write_file("src/utils.py", content)
                run(["git", "add", "src/utils.py"], cwd=repo_dir, env=env)

            msg = f"Commit {i}: routine update"

        run(["git", "commit", "-m", msg], cwd=repo_dir, env=env)

        h = run(["git", "rev-parse", "HEAD"], cwd=repo_dir, env=base_env)
        commit_hashes.append(h)
        print(f"  [{i:02d}] {h[:8]} {date_str[:10]} ({author[0]}) {msg[:60]}")

    # Add annotated tag at index 35
    tag_hash = commit_hashes[TAG_INDEX]
    tag_date = make_date(TAG_INDEX)
    tag_env = make_env(ALICE[0], ALICE[1], ALICE[0], ALICE[1], tag_date, base_env)
    run(
        ["git", "tag", "-a", "v1.0", tag_hash,
         "-m", f"Release v1.0 — includes staging credential {SECRET1} for reference"],
        cwd=repo_dir, env=tag_env,
    )
    print(f"\nAnnotated tag v1.0 created at commit index {TAG_INDEX} ({tag_hash[:8]})")

    # Add git note to commit at index 30
    note_hash = commit_hashes[NOTE_INDEX]
    note_env = make_env(ALICE[0], ALICE[1], ALICE[0], ALICE[1], make_date(NOTE_INDEX), base_env)
    run(
        ["git", "notes", "add", "-m",
         f"Security review: {SECRET2} was active during this period and has since been rotated.",
         note_hash],
        cwd=repo_dir, env=note_env,
    )
    print(f"Git note added to commit index {NOTE_INDEX} ({note_hash[:8]})")

    return repo_dir, commit_hashes


def verify(repo_dir, commit_hashes, base_env):
    print("\n--- Verification ---")

    # Commit count
    count = run(["git", "rev-list", "--count", "HEAD"], cwd=repo_dir, env=base_env)
    print(f"Total commits: {count}")
    assert int(count) == NUM_COMMITS, f"Expected {NUM_COMMITS} commits, got {count}"

    # SECRET1 in history
    result = subprocess.run(
        ["git", "log", "-p", "--all", "--notes", "-S", SECRET1],
        cwd=repo_dir, env=base_env, capture_output=True, text=True,
    )
    assert SECRET1 in result.stdout, "SECRET1 not found in git history!"
    print(f"SECRET1 found in git history: YES")

    # SECRET1 in tag message
    tag_info = run(["git", "cat-file", "-p", "v1.0"], cwd=repo_dir, env=base_env)
    assert SECRET1 in tag_info, "SECRET1 not found in tag message!"
    print(f"SECRET1 found in tag v1.0 message: YES")

    # SECRET2 in git notes
    notes_out = run(["git", "log", "--notes", "--format=%N", "HEAD"], cwd=repo_dir, env=base_env)
    assert SECRET2 in notes_out, "SECRET2 not found in git notes!"
    print(f"SECRET2 found in git notes: YES")

    # Note on correct commit
    note_hash = commit_hashes[NOTE_INDEX]
    note_content = run(["git", "notes", "show", note_hash], cwd=repo_dir, env=base_env)
    assert SECRET2 in note_content, f"Note on commit {note_hash[:8]} missing SECRET2!"
    print(f"Note on commit index {NOTE_INDEX} ({note_hash[:8]}): OK")


def package(repo_dir, output_path):
    print(f"\nPackaging repo to: {output_path}")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(repo_dir, arcname=".")
    size = os.path.getsize(output_path)
    print(f"Archive size: {size:,} bytes ({size / 1024:.1f} KB)")
    return size


def main():
    base_env = os.environ.copy()
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"

    repo_dir, commit_hashes = create_repo()

    # Use the repo's own env for verification
    repo_base_env = base_env.copy()
    repo_base_env["HOME"] = repo_dir

    verify(repo_dir, commit_hashes, repo_base_env)

    output_path = SCRIPT_DIR / "repo_small.tgz"
    package(repo_dir, str(output_path))

    shutil.rmtree(repo_dir)
    print(f"\nDone. repo_small.tgz created at: {output_path}")


if __name__ == "__main__":
    main()
