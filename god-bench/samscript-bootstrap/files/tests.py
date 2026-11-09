import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from scaffold import RuntimeFault, run_source


def test_normal_shadow_and_nearest_assignment():
    source = """fn main() { let x = 4; if true { let x = 9; x += 2; print(x); } print(x); }"""
    assert run_source(source) == "11\n4\n"


def test_edge_nested_loop_control():
    source = """fn main() { let i = 0; let score = 0; loop { i += 1; if i == 2 { continue; } let j = 0; loop { j += 1; if j == 2 { break; } score += i; } if i == 3 { break; } } print(score); }"""
    assert run_source(source) == "4\n"


def test_invariant_early_return_unwinds_blocks():
    source = """fn choose(n) { if n > 0 { let n = 99; return n; } return 7; } fn main() { print(choose(1)); print(choose(0)); }"""
    assert run_source(source) == "99\n7\n"


def test_deterministic_rerun():
    source = """fn f(n) { if n == 0 { return 1; } return n * f(n - 1); } fn main() { print(f(6)); }"""
    assert run_source(source) == run_source(source) == "720\n"
