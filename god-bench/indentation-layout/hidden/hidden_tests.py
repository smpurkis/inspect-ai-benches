import os
import random
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

HARNESS = "/tmp/indentation-layout-build/layout-harness"
CANDIDATE = "/app/files/src/Layout.hs"


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


def layout(source):
    result = run(source)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def lex(source):
    result = []
    names = {"let": "let", "where": "where", "in": "in"}
    punctuation = {"=": "=", "(": "(", ")": ")", "{": "{", "}": "}", ";": ";"}
    for line_no, raw in enumerate(source.splitlines(), 1):
        text = raw.split("--", 1)[0]
        pos = 0
        while pos < len(text):
            if text[pos] == " ":
                pos += 1
            elif text[pos].isalpha() or text[pos] == "_":
                match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[pos:])
                word = match.group(0)
                result.append((line_no, pos + 1, names.get(word, "id:" + word)))
                pos += len(word)
            elif text[pos] in punctuation:
                result.append((line_no, pos + 1, punctuation[text[pos]]))
                pos += 1
            else:
                raise ValueError("bad generated source")
    return result


def oracle(source):
    incoming = lex(source)
    if not incoming:
        return []
    # Contexts are (kind, indentation), with None indentation for explicit braces.
    contexts = [("root", incoming[0][1])]
    output = ["<open>"]
    pending = None
    previous_line = 0
    previous_token = None

    for line_no, column, token in incoming:
        just_opened = False
        if pending is not None:
            if token != "{":
                contexts.append((pending, column))
                output.append("<open>")
                just_opened = True
            pending = None

        new_line = previous_line != 0 and line_no != previous_line
        if new_line and not just_opened and token != "in":
            popped = False
            while contexts[-1][1] is not None and column < contexts[-1][1]:
                contexts.pop()
                output.append("<close>")
                popped = True
                if not contexts:
                    raise ValueError("BadDedent")
            if contexts[-1][1] is not None:
                indent = contexts[-1][1]
                if column > indent:
                    if popped:
                        raise ValueError("BadDedent")
                elif column == indent:
                    if token not in ("in", "}", ";") and previous_token not in ("{", ";"):
                        output.append("<semi>")
                else:
                    raise ValueError("BadDedent")

        if token == "in":
            index = next(
                (i for i in range(len(contexts) - 1, -1, -1) if contexts[i][0] == "let"),
                None,
            )
            if index is not None:
                if any(kind == "explicit" for kind, _ in contexts[index + 1:]):
                    raise ValueError("in crosses explicit block")
                while len(contexts) - 1 >= index:
                    contexts.pop()
                    output.append("<close>")
        elif token == "}":
            while contexts and contexts[-1][0] != "explicit":
                contexts.pop()
                output.append("<close>")
            if not contexts:
                raise ValueError("UnexpectedClose")
            contexts.pop()

        output.append(token)
        if token in ("let", "where"):
            pending = token
        elif token == "{":
            contexts.append(("explicit", None))
        previous_line = line_no
        previous_token = token

    if pending is not None:
        raise ValueError("MissingBlock")
    if any(kind == "explicit" for kind, _ in contexts):
        raise ValueError("UnclosedExplicit")
    while contexts:
        contexts.pop()
        output.append("<close>")
    return output


def test_generated_nested_layout_matches_independent_oracle():
    rng = random.Random(0x1A70)
    for case in range(80):
        root = rng.randint(1, 5)
        inner = root + rng.randint(1, 6)
        deep = inner + rng.randint(1, 5)
        count = rng.randint(1, 4)
        lines = [" " * (root - 1) + f"result{case} = let"]
        for index in range(count):
            if index == count // 2 and case % 3 == 0:
                lines.extend([
                    " " * (inner - 1) + f"v{index} = let",
                    " " * (deep - 1) + "z = atom",
                    " " * (inner - 1) + "in z",
                ])
            else:
                lines.append(" " * (inner - 1) + f"v{index} = atom")
            if rng.randrange(3) == 0:
                lines.append(" " * rng.randrange(0, 5) + "-- generated comment")
                lines.append("")
        lines.append(" " * (root - 1) + "in v0")
        source = "\n".join(lines) + "\n"
        assert layout(source) == oracle(source)
        assert run(source, "parse").returncode == 0


@pytest.mark.parametrize(
    "source",
    [
        "x = let { a = one; b = let\n  c = two\n  d = three\nin c } in b\n",
        "x = one where\n  a = two\n  b = three\ny = four\n",
        "x = (let a = one in a)\n",
        "x = let\n  a = one where\n    p = two\n    q = three\n  b = a\nin b\n",
        "x = let { a = one; b = two } in b\ny = three\n",
    ],
)
def test_layout_variants_and_parser(source):
    assert layout(source) == oracle(source)
    assert run(source, "parse").stdout == "ok\n"


def test_comments_blank_lines_and_translation_are_metamorphic():
    base = "x = let\n  a = one\n  b = two\nin b\ny = three\n"
    decorated = "    x = let -- open\n\n      a = one\n  -- invisible\n      b = two\n    in b\n    y = three -- tail\n"
    assert layout(base) == layout(decorated) == oracle(base)


@pytest.mark.parametrize(
    "source,error",
    [
        ("x = let\n    a = one\n  b = two\nin a\n", "BadDedent"),
        ("x = one where\n  y = two\n z = three\n", "BadDedent"),
        ("x = one }\n", "UnexpectedClose"),
        ("x = let { a = one\n", "UnclosedExplicit"),
        ("x = let\n", "MissingBlock"),
        ("x = one\n\ty = two\n", "tabs are not permitted"),
    ],
)
def test_malformed_dedents_and_boundaries(source, error):
    result = run(source)
    assert result.returncode != 0
    assert error in result.stderr


def test_explicit_block_suspends_outer_indentation():
    source = "x = let {\na = one;\n b = two\n} in b\n"
    assert layout(source) == oracle(source)


def test_deterministic_generated_replays():
    source = "root = let\n   a = one\n   b = let c = two in c\nin b\n"
    observations = [run(source) for _ in range(4)]
    assert all(item.returncode == 0 for item in observations)
    assert len({(item.stdout, item.stderr) for item in observations}) == 1


def test_candidate_is_the_only_compiled_layout_kernel():
    source = open(CANDIDATE, encoding="utf-8").read()
    assert "module Layout" in source
    assert "insertLayout" in source
    assert not os.path.islink(CANDIDATE)
    declarations = sum(
        path.read_text(encoding="utf-8").count("insertLayout ::")
        for path in Path("/tmp/indentation-layout-build").glob("*.hs")
    )
    assert declarations == 1
