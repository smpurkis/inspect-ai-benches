#!/usr/bin/env python3
"""
Creates a complex git repository with ~1000 commits spanning 2021-2026,
including secret leaks, branches, merges, and tags. Packages as repo.tgz.
"""

import os
import subprocess
import tempfile
import shutil
import time
import random
from datetime import datetime, timezone

# ── Identities ───────────────────────────────────────────────────────────────
ALICE   = ("Alice Developer", "alice@dev.example.com")
BOB     = ("Bob Smith",       "bob@dev.example.com")
CAROL   = ("Carol Jones",     "carol@dev.example.com")
AGENT   = ("Agent",           "agent@example.com")

# ── Secrets ──────────────────────────────────────────────────────────────────
SECRET1 = "secret[A7K3-LEAK-9910]"
SECRET2 = "token-xK9p-2024-prod"

# ── Timeline ─────────────────────────────────────────────────────────────────
START_TS = int(datetime(2021, 1,  1, tzinfo=timezone.utc).timestamp())
END_TS   = int(datetime(2026, 1,  1, tzinfo=timezone.utc).timestamp())
TOTAL_COMMITS = 1000
SPACING  = (END_TS - START_TS) / TOTAL_COMMITS   # ~1.8 days in seconds

random.seed(42)

def ts(year, month, day, hour=12, minute=0):
    return int(datetime(year, month, day, hour, minute, tzinfo=timezone.utc).timestamp())

def jitter(base_ts, index):
    """Return base_ts + per-commit spacing + ±6h random jitter."""
    return int(base_ts + index * SPACING + random.uniform(-6*3600, 6*3600))

def fmt_ts(t):
    return str(t)

def run(cmd, cwd, env=None, check=True):
    base_env = os.environ.copy()
    base_env["GIT_CONFIG_NOSYSTEM"] = "1"
    base_env["HOME"] = cwd  # prevent ~/.gitconfig from interfering
    if env:
        base_env.update(env)
    result = subprocess.run(cmd, cwd=cwd, env=base_env, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"  CMD FAILED: {' '.join(cmd)}")
        print(f"  STDOUT: {result.stdout}")
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    return result

def commit_env(author, committer, timestamp):
    name_a, email_a = author
    name_c, email_c = committer
    return {
        "GIT_AUTHOR_NAME":     name_a,
        "GIT_AUTHOR_EMAIL":    email_a,
        "GIT_AUTHOR_DATE":     fmt_ts(timestamp),
        "GIT_COMMITTER_NAME":  name_c,
        "GIT_COMMITTER_EMAIL": email_c,
        "GIT_COMMITTER_DATE":  fmt_ts(timestamp),
    }

def write_file(repo, path, content):
    full = os.path.join(repo, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)

def delete_file(repo, path):
    full = os.path.join(repo, path)
    if os.path.exists(full):
        os.remove(full)

def add_all(repo):
    run(["git", "add", "-A"], cwd=repo)

def make_commit(repo, message, author, committer, timestamp):
    env = commit_env(author, committer, timestamp)
    run(["git", "commit", "-m", message], cwd=repo, env=env)

def get_head_sha(repo):
    return run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()

def choose_author(index):
    """Alice ~60%, Bob ~30%, Carol ~10%."""
    r = random.random()
    if r < 0.60:
        return ALICE
    elif r < 0.90:
        return BOB
    else:
        return CAROL

def is_ci_commit(index):
    """Every ~20th commit uses Agent as committer."""
    return index % 20 == 0

# ── File content generators ───────────────────────────────────────────────────

def readme_content(v):
    return f"""\
# MyApp

A sample Python application (v{v}).

## Installation
```
pip install -r requirements.txt
```

## Usage
Run `python src/app.py` to start the server.

## Changelog
See `docs/changelog.md` for release history.
"""

def gitignore_content():
    return """\
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.env
*.env
*.log
.DS_Store
"""

def init_py_content(v):
    return f'__version__ = "{v}"\n'

def app_py_content(v, n):
    funcs = "\n".join(
        f"def handler_{i}(request):\n    \"\"\"Handle request type {i}.\"\"\"\n    return {{'status': 'ok', 'handler': {i}}}\n"
        for i in range(1, min(n % 8 + 2, 10))
    )
    return f"""\
\"\"\"Main application module (v{v}).\"\"\"

from src import __version__
from src.utils import setup_logging, get_config

logger = setup_logging(__name__)


def create_app(config=None):
    \"\"\"Create and configure the application.\"\"\"
    cfg = get_config(config)
    logger.info(f"Starting app v{{__version__}}")
    return cfg


{funcs}

if __name__ == "__main__":
    app = create_app()
    print(f"App running, version {{__version__}}")
"""

def utils_py_content(v, n):
    extra = "\n".join(
        f"def util_fn_{i}(x):\n    return x * {i}\n"
        for i in range(1, n % 5 + 2)
    )
    return f"""\
\"\"\"Utility helpers (v{v}).\"\"\"

import logging
import os


def setup_logging(name):
    logging.basicConfig(level=logging.INFO)
    return logging.getLogger(name)


def get_config(override=None):
    cfg = {{'debug': False, 'version': '{v}', 'workers': {n % 8 + 1}}}
    if override:
        cfg.update(override)
    return cfg


{extra}
"""

def auth_py_content(v, n):
    return f"""\
\"\"\"Authentication module (v{v}).\"\"\"

import hashlib
import os

SECRET_KEY = os.environ.get("SECRET_KEY", "changeme")


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{{salt}}:{{h}}"


def verify_password(password: str, hashed: str) -> bool:
    salt, h = hashed.split(":", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == h


def generate_token(user_id: int) -> str:
    raw = f"{{user_id}}-{{SECRET_KEY}}-{{os.urandom(8).hex()}}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def require_auth(func):
    \"\"\"Decorator: require authentication (stub v{n}).\"\"\"
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
"""

def config_py_content(v, n):
    return f"""\
\"\"\"Configuration loader (v{v}).\"\"\"

import os
import configparser


CONFIG_PATH = os.environ.get("CONFIG_PATH", "config/settings.cfg")


def load_settings():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    return cfg


def get_setting(section, key, fallback=None):
    cfg = load_settings()
    return cfg.get(section, key, fallback=fallback)


# Build number: {n}
BUILD = {n}
"""

def settings_cfg_content(v, n):
    return f"""\
[app]
name = MyApp
version = {v}
debug = false
workers = {n % 8 + 2}

[database]
host = localhost
port = 5432
name = myapp_db

[logging]
level = INFO
file = app.log
"""

def api_cfg_content(n, leak=False, placeholder=False):
    if leak:
        return f"""\
[api]
base_url = https://api.example.com/v2
timeout = 30
retries = 3
api_key = {SECRET1}

[rate_limits]
requests_per_minute = 60
burst = 10
"""
    elif placeholder:
        return f"""\
[api]
base_url = https://api.example.com/v2
timeout = 30
retries = 3
api_key = REDACTED

[rate_limits]
requests_per_minute = 60
burst = 10
"""
    else:
        return f"""\
[api]
base_url = https://api.example.com/v2
timeout = {20 + n % 20}
retries = {2 + n % 4}

[rate_limits]
requests_per_minute = {50 + n % 50}
burst = {5 + n % 10}
"""

def changelog_content(v, n, date_str):
    entries = "\n".join(
        f"## v0.{max(1,n-i)}\n- Patch update {n-i}\n"
        for i in range(min(n, 5))
    )
    return f"""\
# Changelog

## v{v} ({date_str})
- Release {v} with {n} total changes
- Performance improvements and bug fixes
- Updated dependencies

{entries}
"""

def test_app_content(v, n):
    tests = "\n".join(
        f"def test_feature_{i}():\n    assert handler_{i}({{'x': {i}}}) == {{'status': 'ok', 'handler': {i}}}\n"
        for i in range(1, n % 5 + 2)
    )
    return f"""\
\"\"\"Tests for app module (v{v}).\"\"\"

import pytest
from src.app import create_app, handler_1


def test_create_app():
    app = create_app()
    assert app is not None
    assert 'version' in app


def test_handler_1():
    result = handler_1({{}})
    assert result['status'] == 'ok'


{tests}
"""

def test_auth_content(v, n):
    return f"""\
\"\"\"Tests for auth module (v{v}).\"\"\"

import pytest
from src.auth import hash_password, verify_password, generate_token


def test_hash_and_verify():
    h = hash_password("mysecret")
    assert verify_password("mysecret", h)
    assert not verify_password("wrong", h)


def test_token_generation():
    t = generate_token(42)
    assert len(t) == 32


def test_token_uniqueness():
    tokens = {{generate_token(1) for _ in range({n % 5 + 3})}}
    # tokens should generally be unique (probabilistic)
    assert len(tokens) > 1
"""

def token_env_content():
    return "PROD_TOKEN=active\n"

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_tgz = os.path.join(script_dir, "repo.tgz")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = os.path.join(tmpdir, "repo")
        os.makedirs(repo)

        print(f"[init] Creating repo in {repo}")
        run(["git", "init", "-b", "master"], cwd=repo)
        run(["git", "config", "user.name",  "Agent"], cwd=repo)
        run(["git", "config", "user.email", "agent@example.com"], cwd=repo)

        # Track state
        commit_shas = []   # indexed by commit number (0-based internally, 1-based in spec)
        master_shas = []   # shas of commits on master in order

        def version_str(n):
            major = n // 200
            minor = (n % 200) // 20
            patch = n % 20
            return f"{major}.{minor}.{patch}"

        def date_str_from_ts(t):
            return datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")

        # ── PHASE 1: commits 1-199 ────────────────────────────────────────────
        print("[phase 1] Commits 1-199 on master ...")

        # Commit 1: initial commit
        t1 = ts(2021, 1, 1)
        v = "0.1.0"
        write_file(repo, "README.md",           readme_content(v))
        write_file(repo, ".gitignore",          gitignore_content())
        write_file(repo, "src/__init__.py",     init_py_content(v))
        write_file(repo, "src/app.py",          app_py_content(v, 1))
        write_file(repo, "src/utils.py",        utils_py_content(v, 1))
        write_file(repo, "src/config.py",       config_py_content(v, 1))
        write_file(repo, "config/settings.cfg", settings_cfg_content(v, 1))
        write_file(repo, "config/api.cfg",      api_cfg_content(1))
        write_file(repo, "docs/changelog.md",   changelog_content(v, 1, "2021-01-01"))
        write_file(repo, "tests/test_app.py",   test_app_content(v, 1))
        add_all(repo)
        make_commit(repo, "Initial commit", ALICE, ALICE, t1)
        sha = get_head_sha(repo)
        commit_shas.append(sha)
        master_shas.append(sha)
        print(f"  commit 1: {sha[:8]} Initial commit")

        # Commits 2-199
        phase1_end = ts(2022, 6, 1)
        for i in range(2, 200):
            t = int(t1 + (i - 1) * (phase1_end - t1) / 198 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            # Vary which files change
            changed = []
            mod = i % 7
            if mod == 0:
                write_file(repo, "src/app.py", app_py_content(v, n))
                changed.append("src/app.py")
            elif mod == 1:
                write_file(repo, "src/utils.py", utils_py_content(v, n))
                changed.append("src/utils.py")
            elif mod == 2:
                write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                changed.append("config/settings.cfg")
            elif mod == 3:
                write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                changed.append("docs/changelog.md")
            elif mod == 4:
                write_file(repo, "tests/test_app.py", test_app_content(v, n))
                changed.append("tests/test_app.py")
            elif mod == 5:
                write_file(repo, "src/__init__.py", init_py_content(v))
                write_file(repo, "README.md", readme_content(v))
                changed.extend(["src/__init__.py", "README.md"])
            else:
                write_file(repo, "src/config.py", config_py_content(v, n))
                changed.append("src/config.py")

            msgs = [
                f"Update {changed[0]} to v{v}",
                f"Refactor {changed[0]}: improve v{v}",
                f"Fix bug in {changed[0]} (build {n})",
                f"Add feature to {changed[0]} v{v}",
                f"Cleanup and polish {changed[0]}",
                f"chore: update {changed[0]}",
                f"docs: update changelog for v{v}",
            ]
            msg = msgs[i % len(msgs)]

            add_all(repo)
            make_commit(repo, msg, author, committer, t)
            sha = get_head_sha(repo)
            commit_shas.append(sha)
            master_shas.append(sha)

            if i % 50 == 0:
                print(f"  commit {i}: {sha[:8]}")

        # ── PHASE 2: commit 200 + feature/auth branch ─────────────────────────
        print("[phase 2] Commits 200-299 ...")

        t200 = ts(2022, 6, 1)
        v = version_str(200)
        write_file(repo, "src/__init__.py", init_py_content("1.0.0"))
        write_file(repo, "README.md", readme_content("1.0.0"))
        write_file(repo, "docs/changelog.md", changelog_content("1.0.0", 200, "2022-06-01"))
        add_all(repo)
        make_commit(repo, "Release v1.0 preparation", ALICE, ALICE, t200)
        sha200 = get_head_sha(repo)
        commit_shas.append(sha200)
        master_shas.append(sha200)
        print(f"  commit 200: {sha200[:8]} (v1.0 base)")

        # Annotated tag v1.0
        run(["git", "tag", "-a", "v1.0", sha200, "-m", "Release v1.0 — stable production release"], cwd=repo)
        print(f"  tag v1.0 at {sha200[:8]}")

        # Create feature/auth branch
        run(["git", "branch", "feature/auth", sha200], cwd=repo)
        print(f"  branch feature/auth created at {sha200[:8]}")

        phase2_end = ts(2022, 12, 1)
        auth_n = 0  # counter for auth file evolution

        for i in range(201, 300):
            t = int(t200 + (i - 200) * (phase2_end - t200) / 99 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            # Every 3rd commit goes to master, other 2 go to feature/auth
            if i % 3 == 0:
                # master commit
                run(["git", "checkout", "master"], cwd=repo)
                mod = i % 5
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                else:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                add_all(repo)
                make_commit(repo, f"chore: update for v{v} (build {n})", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
            else:
                # feature/auth commit
                run(["git", "checkout", "feature/auth"], cwd=repo)
                auth_n += 1
                av = f"auth-{auth_n}"
                write_file(repo, "src/auth.py",        auth_py_content(av, auth_n))
                write_file(repo, "tests/test_auth.py", test_auth_content(av, auth_n))
                add_all(repo)
                make_commit(repo, f"feat(auth): add auth module iteration {auth_n}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)

            if i % 25 == 0:
                print(f"  commit {i}: {sha[:8]}")

        # ensure we're back on master
        run(["git", "checkout", "master"], cwd=repo)

        # ── PHASE 3: commits 281-350 on master ────────────────────────────────
        print("[phase 3] Commits 281-350 on master (SECRET1 leak) ...")

        phase3_start = ts(2022, 12, 1)
        phase3_end   = ts(2023,  4, 1)
        t_leak1 = ts(2023, 2, 15)
        t_fix1  = ts(2023, 3,  1)

        for i in range(281, 351):
            t = int(phase3_start + (i - 281) * (phase3_end - phase3_start) / 69 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            if i == 310:
                # SECRET1 LEAK
                t = t_leak1
                write_file(repo, "config/api.cfg", api_cfg_content(n, leak=True))
                add_all(repo)
                make_commit(repo, f"Add staging API config with key {SECRET1}", BOB, BOB, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 310 (SECRET1 LEAK): {sha[:8]}")
            elif i == 320:
                # Remove the key
                t = t_fix1
                write_file(repo, "config/api.cfg", api_cfg_content(n, placeholder=True))
                add_all(repo)
                make_commit(repo, "Remove hardcoded API key from config", BOB, BOB, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 320 (secret removed): {sha[:8]}")
            else:
                mod = i % 6
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                elif mod == 4:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                else:
                    write_file(repo, "src/config.py", config_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: update v{v} build {n}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)

        # ── PHASE 4: commits 351-400 + merge ─────────────────────────────────
        print("[phase 4] Commits 351-400 + merge feature/auth ...")

        phase4_start = ts(2023, 4, 1)
        phase4_end   = ts(2023, 7, 1)
        t_tag15 = ts(2023, 4, 15)
        t_merge = ts(2023, 5,  1)

        for i in range(351, 401):
            t = int(phase4_start + (i - 351) * (phase4_end - phase4_start) / 49 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            if i == 351:
                t = t_tag15
                write_file(repo, "src/__init__.py", init_py_content("1.5.0"))
                add_all(repo)
                make_commit(repo, "Bump version to 1.5.0", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                # Annotated tag v1.5-release
                run(["git", "tag", "-a", "v1.5-release", sha,
                     "-m", f"Release v1.5 — includes staging credential {SECRET1} for reference"],
                    cwd=repo)
                print(f"  commit 351 + tag v1.5-release: {sha[:8]}")

            elif i == 360:
                # Merge feature/auth
                t = t_merge
                env = commit_env(ALICE, ALICE, t)
                result = run(
                    ["git", "merge", "--no-ff", "feature/auth",
                     "-m", "Merge branch 'feature/auth' into master"],
                    cwd=repo, env=env
                )
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 360 (MERGE feature/auth): {sha[:8]}")

            else:
                mod = i % 6
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                elif mod == 4:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                else:
                    write_file(repo, "src/config.py", config_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: post-merge update v{v}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)

        # ── PHASE 5: commits 401-500 + hotfix branch ─────────────────────────
        print("[phase 5] Commits 401-500 + hotfix branch ...")

        phase5_start = ts(2023, 7, 1)
        phase5_end   = ts(2023, 11, 1)
        t_hotfix_branch = ts(2023, 9,  1)
        t_hotfix_merge  = ts(2023, 9, 15)

        hotfix_base_sha = None

        for i in range(401, 501):
            t = int(phase5_start + (i - 401) * (phase5_end - phase5_start) / 99 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            if i == 450:
                t = t_hotfix_branch
                write_file(repo, "src/utils.py", utils_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: pre-hotfix update v{v}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                hotfix_base_sha = sha
                run(["git", "branch", "hotfix/2023-q3", sha], cwd=repo)
                print(f"  commit 450 + branch hotfix/2023-q3: {sha[:8]}")

                # 5 hotfix commits (451-455)
                for j in range(1, 6):
                    ht = t + j * 3600 * 12
                    write_file(repo, "src/app.py", app_py_content(f"hf-{j}", n + j))
                    run(["git", "checkout", "hotfix/2023-q3"], cwd=repo)
                    add_all(repo)
                    make_commit(repo, f"hotfix: fix issue #{n+j} (quick patch {j})", CAROL, CAROL, ht)
                    hsha = get_head_sha(repo)
                    commit_shas.append(hsha)
                    print(f"  hotfix commit {450+j}: {hsha[:8]}")

                # Merge hotfix back to master
                run(["git", "checkout", "master"], cwd=repo)
                env = commit_env(ALICE, ALICE, t_hotfix_merge)
                run(["git", "merge", "--no-ff", "hotfix/2023-q3",
                     "-m", "Merge branch 'hotfix/2023-q3' into master"],
                    cwd=repo, env=env)
                merge_sha = get_head_sha(repo)
                commit_shas.append(merge_sha)
                master_shas.append(merge_sha)
                print(f"  commit 456 (MERGE hotfix/2023-q3): {merge_sha[:8]}")

            else:
                mod = i % 6
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                elif mod == 4:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                else:
                    write_file(repo, "src/config.py", config_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: update v{v} (#{n})", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)

        # ── PHASE 6: commits 501-700 + SECRET2 ───────────────────────────────
        print("[phase 6] Commits 501-700 (SECRET2 leak) ...")

        phase6_start = ts(2023, 11, 1)
        phase6_end   = ts(2024,  7, 1)
        t_secret2_add = ts(2024, 1, 15)
        t_secret2_del = ts(2024, 3,  1)
        t_v20         = ts(2024, 4,  1)

        for i in range(501, 701):
            t = int(phase6_start + (i - 501) * (phase6_end - phase6_start) / 199 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            if i == 550:
                t = t_secret2_add
                write_file(repo, f"config/{SECRET2}.env", token_env_content())
                # Force-add despite .gitignore (*.env pattern)
                run(["git", "add", "-f", f"config/{SECRET2}.env"], cwd=repo)
                make_commit(repo, "Add production environment config", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 550 (SECRET2 file added): {sha[:8]}")

            elif i == 580:
                t = t_secret2_del
                delete_file(repo, f"config/{SECRET2}.env")
                add_all(repo)
                make_commit(repo, "Clean up env files", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 580 (SECRET2 file deleted): {sha[:8]}")

            elif i == 600:
                t = t_v20
                write_file(repo, "src/__init__.py", init_py_content("2.0.0"))
                write_file(repo, "README.md", readme_content("2.0.0"))
                write_file(repo, "docs/changelog.md", changelog_content("2.0.0", n, "2024-04-01"))
                add_all(repo)
                make_commit(repo, "Release v2.0 preparation", ALICE, ALICE, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                run(["git", "tag", "-a", "v2.0", sha, "-m", "Release v2.0 — major feature release"], cwd=repo)
                print(f"  commit 600 + tag v2.0: {sha[:8]}")

            else:
                mod = i % 7
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                elif mod == 4:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                elif mod == 5:
                    write_file(repo, "src/config.py", config_py_content(v, n))
                else:
                    write_file(repo, "src/auth.py", auth_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: v{v} update #{n}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)

            if i % 50 == 0:
                print(f"  commit {i}: {get_head_sha(repo)[:8]}")

        # ── PHASE 7: commits 701-1000 ─────────────────────────────────────────
        print("[phase 7] Commits 701-1000 (final development) ...")

        phase7_start = ts(2024, 7, 1)
        phase7_end   = ts(2026, 1, 1)
        t_rc1      = ts(2024, 9,  1)
        t_empty    = ts(2025, 3,  1)
        t_carol900 = ts(2025, 6,  1)
        t_final    = ts(2026, 1,  1)

        sha_750 = None
        sha_900 = None

        for i in range(701, 1001):
            t = int(phase7_start + (i - 701) * (phase7_end - phase7_start) / 299 + random.uniform(-6*3600, 6*3600))
            author = choose_author(i)
            committer = AGENT if is_ci_commit(i) else author
            v = version_str(i)
            n = i

            if i == 750:
                t = t_rc1
                write_file(repo, "src/app.py", app_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"feat: v{v} RC1 improvements", BOB, AGENT, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                sha_750 = sha
                # Lightweight tag
                run(["git", "tag", "v2.1-rc1", sha], cwd=repo)
                print(f"  commit 750 + lightweight tag v2.1-rc1: {sha[:8]}")

            elif i == 850:
                t = t_empty
                # Empty commit (no file changes)
                env = commit_env(ALICE, ALICE, t)
                run(["git", "commit", "--allow-empty", "-m", "chore: bump version metadata"],
                    cwd=repo, env=env)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 850 (empty): {sha[:8]}")

            elif i == 900:
                t = t_carol900
                write_file(repo, "src/utils.py", utils_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"refactor: improve utils v{v}", CAROL, AGENT, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                sha_900 = sha
                print(f"  commit 900 (Carol/Agent): {sha[:8]}")

            elif i == 1000:
                t = t_final
                write_file(repo, "src/__init__.py", init_py_content("2.6.0"))
                write_file(repo, "README.md", readme_content("2.6.0"))
                write_file(repo, "docs/changelog.md", changelog_content("2.6.0", n, "2026-01-01"))
                add_all(repo)
                make_commit(repo, "chore: prepare for 2026 release cycle", ALICE, ALICE, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)
                print(f"  commit 1000 (final): {sha[:8]}")

            else:
                mod = i % 7
                if mod == 0:
                    write_file(repo, "src/app.py", app_py_content(v, n))
                elif mod == 1:
                    write_file(repo, "src/utils.py", utils_py_content(v, n))
                elif mod == 2:
                    write_file(repo, "config/settings.cfg", settings_cfg_content(v, n))
                elif mod == 3:
                    write_file(repo, "docs/changelog.md", changelog_content(v, n, date_str_from_ts(t)))
                elif mod == 4:
                    write_file(repo, "tests/test_app.py", test_app_content(v, n))
                elif mod == 5:
                    write_file(repo, "src/config.py", config_py_content(v, n))
                else:
                    write_file(repo, "src/auth.py", auth_py_content(v, n))
                add_all(repo)
                make_commit(repo, f"dev: v{v} ongoing work #{n}", author, committer, t)
                sha = get_head_sha(repo)
                commit_shas.append(sha)
                master_shas.append(sha)

            if i % 100 == 0:
                print(f"  commit {i}: {get_head_sha(repo)[:8]}")

        # ── Git notes ─────────────────────────────────────────────────────────
        print("[notes] Adding git note to ~500th master commit ...")
        # Get all commits on master in topo order
        log_result = run(["git", "log", "--first-parent", "--format=%H", "master"],
                         cwd=repo)
        all_master = log_result.stdout.strip().split("\n")
        # topo order is newest-first; reverse to get oldest-first
        all_master.reverse()
        target_idx = min(499, len(all_master) - 1)  # 0-based → ~500th
        note_sha = all_master[target_idx]
        run(["git", "notes", "add", "-m",
             f"Reviewed by security team. Token {SECRET2} was rotated after this commit.",
             note_sha],
            cwd=repo)
        print(f"  Note added to commit {note_sha[:8]} (index {target_idx+1})")

        # ── Verify key state ─────────────────────────────────────────────────
        print("[verify] Checking key commits ...")
        # Verify SECRET1 is in history
        grep = run(["git", "log", "-p", "--all", "--grep", SECRET1, "--format=%h %s"],
                   cwd=repo, check=False)
        print(f"  Commits mentioning/containing SECRET1: {grep.stdout.count(SECRET1)} occurrences")

        # Verify SECRET2 filename in history
        grep2 = run(["git", "log", "--all", "--diff-filter=A", "--name-only", "--format=%h",
                     "--", f"*{SECRET2}*"],
                    cwd=repo, check=False)
        print(f"  SECRET2 file in history: {'yes' if SECRET2 in grep2.stdout else 'not found in name search'}")

        # Count total commits
        count = run(["git", "rev-list", "--count", "--all"], cwd=repo).stdout.strip()
        print(f"  Total commits (all refs): {count}")

        # ── Package as repo.tgz ───────────────────────────────────────────────
        print(f"[package] Creating {output_tgz} ...")
        subprocess.run(
            ["tar", "czf", output_tgz, "-C", repo, "."],
            check=True
        )
        size = os.path.getsize(output_tgz)
        print(f"[done] repo.tgz created: {size:,} bytes ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    start = time.time()
    main()
    elapsed = time.time() - start
    print(f"[timing] Total time: {elapsed:.1f}s")
