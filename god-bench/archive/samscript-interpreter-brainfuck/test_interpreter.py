"""
Test harness for the SamScript interpreter.

Builds the interpreter via `cargo build --release`, then runs each .sam test
program and asserts that stdout matches the expected output exactly.
"""

import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parent  # directory containing Cargo.toml
BINARY = PROJECT_DIR / "target" / "release" / "samscript"
TESTS_DIR = PROJECT_DIR / "tests"


def setup_module():
    """Build the interpreter before running tests."""
    result = subprocess.run(
        ["cargo", "build", "--release"],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"Build failed:\n{result.stderr}"


def _run(sam_file: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a .sam file through the interpreter and return the result."""
    return subprocess.run(
        [str(BINARY), "run", str(TESTS_DIR / sam_file)],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Individual test functions
# ---------------------------------------------------------------------------


def test_hello():
    r = _run("test_hello.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = "hello world"
    assert r.stdout.strip() == expected


def test_arithmetic():
    r = _run("test_arithmetic.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
2 + 3 = 5
10 - 4 = 6
6 * 7 = 42
10 / 4 = 2.5
17 % 5 = 2
2 ** 10 = 1024
-5 + 3 = -2"""
    assert r.stdout.strip() == expected


def test_variables():
    r = _run("test_variables.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
x = 10
x = 20
y = hello
PI = 3.14159"""
    assert r.stdout.strip() == expected


def test_compound_assign():
    r = _run("test_compound_assign.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
x += 5: 15
x -= 3: 12
x *= 2: 24
x /= 4: 6
y %= 5: 2"""
    assert r.stdout.strip() == expected


def test_strings():
    r = _run("test_strings.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
hello world
Hello, Sam!
1 + 2 = 3
The answer is 42
line1
line2"""
    assert r.stdout.strip() == expected


def test_control_flow():
    r = _run("test_control_flow.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
x > 5
medium
i = 0
i = 1
i = 2
i = 3
i = 4
odd: 1
odd: 3
odd: 5
odd: 7
odd: 9"""
    assert r.stdout.strip() == expected


def test_functions():
    r = _run("test_functions.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
add(3, 4) = 7
5! = 120
10! = 3628800
fib(0) = 0
fib(1) = 1
fib(8) = 21"""
    assert r.stdout.strip() == expected


def test_booleans():
    r = _run("test_booleans.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
true and false = false
true or false = true
not true = false
not false = true
1 == 1: true
1 != 2: true
3 < 5: true
5 > 3: true
3 <= 3: true
3 >= 4: false"""
    assert r.stdout.strip() == expected


def test_builtins():
    r = _run("test_builtins.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
str(42) = 42
str(3.14) = 3.14
len of hello = 5
type(42) = number
type(hello) = string
type(true) = bool
type(none) = none
num(123) = 123"""
    assert r.stdout.strip() == expected


def test_unary_negation():
    r = _run("test_unary_negation.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
abs(-7) = 7
abs(5) = 5
-x = 10
x = -10"""
    assert r.stdout.strip() == expected


def test_number_formatting():
    r = _run("test_number_formatting.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = """\
10
10
3.14
0
-5
1000000"""
    assert r.stdout.strip() == expected


def test_string_concat_building():
    r = _run("test_string_concat_building.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = "countdown: 5, 4, 3, 2, 1"
    assert r.stdout.strip() == expected


def test_comments():
    r = _run("test_comments.sam")
    assert r.returncode == 0, f"Process failed:\n{r.stderr}"
    expected = "x = 10"
    assert r.stdout.strip() == expected
