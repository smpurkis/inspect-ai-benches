import os
import subprocess
import tempfile

HARNESS = "/tmp/indentation-layout-build/layout-harness"


def run(source, mode="layout"):
    with tempfile.NamedTemporaryFile("w", delete=False) as stream:
        stream.write(source)
        path = stream.name
    try:
        return subprocess.run(
            [HARNESS, mode, path], text=True, capture_output=True, timeout=5
        )
    finally:
        os.unlink(path)


def tokens(source):
    result = run(source)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_normal_nested_let():
    source = "answer = let\n  x = one\n  y = two\nin x\n"
    assert tokens(source) == [
        "<open>", "id:answer", "=", "let", "<open>", "id:x", "=",
        "id:one", "<semi>", "id:y", "=", "id:two", "<close>", "in",
        "id:x", "<close>",
    ]
    assert run(source, "parse").stdout == "ok\n"


def test_edge_explicit_braces_and_comments():
    source = "x = let { a = one; b = two } in b -- ignored\n"
    expected = ["<open>", "id:x", "=", "let", "{", "id:a", "=", "id:one",
                ";", "id:b", "=", "id:two", "}", "in", "id:b", "<close>"]
    assert tokens(source) == expected


def test_invariant_indentation_translation():
    assert tokens("x = one\ny = two\n") == tokens("   x = one\n   y = two\n")


def test_deterministic_rerun_and_bad_dedent():
    source = "x = let\n    a = one\n  b = two\nin a\n"
    first = run(source)
    second = run(source)
    assert (first.returncode, first.stdout, first.stderr) == (
        second.returncode, second.stdout, second.stderr
    )
    assert first.returncode != 0
    assert "BadDedent" in first.stderr
