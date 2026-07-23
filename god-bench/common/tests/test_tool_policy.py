from __future__ import annotations

import hashlib

import pytest

from tool_policy import (
    ActionClass,
    action_cost,
    classify_action,
    editable_fingerprint,
    is_editable_path,
    is_no_progress_test,
    normalize_command,
    normalize_query,
    posix_glob_match,
    read_cache_key,
    search_cache_key,
)


def test_normalization_collapses_equivalent_commands_and_queries() -> None:
    assert normalize_command('pytest   -q  "tests public.py"') == "pytest -q 'tests public.py'"
    assert normalize_command("rg TODO src && pytest -q") == "rg TODO src && pytest -q"
    assert normalize_query("  timezone\n   ordering ") == "timezone ordering"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("rg TODO /app/files", ActionClass.SEARCH),
        ("cat /app/files/main.py", ActionClass.READ),
        ("apply_patch patch.diff", ActionClass.EDIT),
        ("cargo build --release", ActionClass.BUILD),
        ("pytest -q /app/files/tests_public.py", ActionClass.PUBLIC_TEST),
        ("python -m pytest -q /app/files/tests.py", ActionClass.PUBLIC_TEST),
        ("pytest -q", ActionClass.FULL_TEST),
        ("pytest /app/hidden/hidden_tests.py", ActionClass.FULL_TEST),
    ],
)
def test_action_classification(command, expected) -> None:
    assert classify_action(command) is expected


def test_exact_declared_public_command_overrides_generic_classification() -> None:
    assert classify_action(
        "python check_solution.py",
        public_test_command="python  check_solution.py",
    ) is ActionClass.PUBLIC_TEST


@pytest.mark.parametrize(
    ("action", "before", "at_escalation"),
    [
        (ActionClass.SEARCH, (7, 1), (8, 2)),
        (ActionClass.READ, (11, 1), (12, 2)),
        (ActionClass.BUILD, (4, 2), (5, 3)),
        (ActionClass.PUBLIC_TEST, (1, 5), (2, 8)),
        (ActionClass.FULL_TEST, (0, 8), (1, 13)),
    ],
)
def test_weighted_cost_escalates_at_schedule_boundary(action, before, at_escalation) -> None:
    prior_count, expected = before
    assert action_cost(action, prior_count) == expected
    prior_count, expected = at_escalation
    assert action_cost(action, prior_count) == expected


def test_fixed_action_costs() -> None:
    assert action_cost(ActionClass.EDIT, 100) == 1
    assert action_cost(ActionClass.NO_PROGRESS) == 8
    assert action_cost(ActionClass.OVERSIZE_READ) == 6


def test_fingerprint_is_sha256_order_independent_and_content_sensitive() -> None:
    first = editable_fingerprint({"b.py": b"b", "a.py": "a"})
    reordered = editable_fingerprint({"a.py": "a", "b.py": b"b"})
    changed = editable_fingerprint({"a.py": "changed", "b.py": b"b"})

    assert first == reordered
    assert first != changed
    assert len(first) == hashlib.sha256().digest_size * 2


def test_fingerprint_framing_avoids_path_content_boundary_collisions() -> None:
    assert editable_fingerprint({"ab": "c"}) != editable_fingerprint({"a": "bc"})
    assert editable_fingerprint({"a": "", "b": "c"}) != editable_fingerprint({"a": "b", "c": ""})


def test_duplicate_read_keys_normalize_paths_but_search_keeps_exact_regex_bytes() -> None:
    assert read_cache_key("./src/../src/main.py", 10, 20) == read_cache_key(
        "src/main.py", 10, 20
    )
    assert search_cache_key(" TODO   item ", "./src", 10) != search_cache_key(
        "TODO item", "src", 10
    )
    assert search_cache_key("TODO item", "./src", 10) == search_cache_key(
        "TODO item", "src", 10
    )
    assert search_cache_key("TODO item", "src", 10) != search_cache_key(
        "TODO item", "src", 20
    )


def test_posix_globs_are_segment_aware_and_double_star_is_recursive() -> None:
    assert posix_glob_match("src/main.py", "src/*.py")
    assert not posix_glob_match("src/nested/main.py", "src/*.py")
    assert posix_glob_match("src/nested/main.py", "src/**/*.py")
    assert posix_glob_match("src/main.py", "src/**/*.py")
    assert is_editable_path("/app/files/src/nested/main.py", ("src/**/*.py",))


def test_invalid_read_range_is_rejected() -> None:
    with pytest.raises(ValueError):
        read_cache_key("main.py", 20, 10)


def test_no_progress_requires_same_test_command_and_fingerprint() -> None:
    fingerprint = editable_fingerprint({"main.py": "before"})
    assert is_no_progress_test(
        "pytest  -q /app/files/tests_public.py",
        fingerprint,
        previous_command="pytest -q /app/files/tests_public.py",
        previous_editable_fingerprint=fingerprint,
    )
    assert not is_no_progress_test(
        "pytest -q /app/files/tests_public.py",
        editable_fingerprint({"main.py": "after"}),
        previous_command="pytest -q /app/files/tests_public.py",
        previous_editable_fingerprint=fingerprint,
    )
    assert not is_no_progress_test(
        "rg TODO /app/files",
        fingerprint,
        previous_command="rg TODO /app/files",
        previous_editable_fingerprint=fingerprint,
    )
