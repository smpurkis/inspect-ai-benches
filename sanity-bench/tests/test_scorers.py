"""Self-tests for all 13 deterministic scorers.

Each scorer is tested with at least one known-good and one known-bad example.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scoring import (
    score_exact_match, score_contains, score_contains_all, score_contains_any,
    score_regex, score_regex_number, score_multiple_choice,
    score_code_exec_python, score_json_schema, score_length_range,
    score_refusal, score_composite,
)


def assert_score(fn, response, cfg, want):
    got, detail = fn(response, cfg)
    ok = abs(got - want) < 0.001
    if not ok:
        print(f"  FAIL: fn={fn.__name__} got={got:.3f} want={want} detail={detail}")
        print(f"    response={response[:80]!r}")
        print(f"    cfg={cfg}")
    return ok


def test_exact_match():
    ok = True
    ok &= assert_score(score_exact_match, "hello world", {"expected": "hello world"}, 1.0)
    ok &= assert_score(score_exact_match, "  Hello   World  ", {"expected": "hello world"}, 1.0)
    ok &= assert_score(score_exact_match, "hello", {"expected": "goodbye"}, 0.0)
    ok &= assert_score(score_exact_match, "Zero.", {"expected": "zero"}, 0.0)  # known brittleness
    print(f"  exact_match: {'PASS' if ok else 'FAIL'}")
    return ok


def test_contains():
    ok = True
    ok &= assert_score(score_contains, "hello world", {"expected": "world"}, 1.0)
    ok &= assert_score(score_contains, "Hello World", {"expected": "world"}, 1.0)
    ok &= assert_score(score_contains, "hello world", {"expected": "goodbye"}, 0.0)
    print(f"  contains: {'PASS' if ok else 'FAIL'}")
    return ok


def test_contains_all():
    ok = True
    ok &= assert_score(score_contains_all, "a b c", {"expected": ["a", "b"]}, 1.0)
    ok &= assert_score(score_contains_all, "a b c", {"expected": ["a", "d"]}, 0.5)
    ok &= assert_score(score_contains_all, "a b c", {"expected": ["d", "e"]}, 0.0)
    print(f"  contains_all: {'PASS' if ok else 'FAIL'}")
    return ok


def test_contains_any():
    ok = True
    ok &= assert_score(score_contains_any, "hello world", {"expected": ["hello"]}, 1.0)
    ok &= assert_score(score_contains_any, "hello world", {"expected": ["goodbye"]}, 0.0)
    ok &= assert_score(score_contains_any, "hello world", {"expected": ["goodbye", "hello"]}, 1.0)
    print(f"  contains_any: {'PASS' if ok else 'FAIL'}")
    return ok


def test_regex():
    ok = True
    ok &= assert_score(score_regex, "hello 42", {"pattern": "\\d+"}, 1.0)
    ok &= assert_score(score_regex, "hello world", {"pattern": "\\d+"}, 0.0)
    ok &= assert_score(score_regex, "Hello", {"pattern": "hello", "flags": ["I"]}, 1.0)
    ok &= assert_score(score_regex, "line1\nline2", {"pattern": "^line2$", "flags": ["M"]}, 1.0)
    print(f"  regex: {'PASS' if ok else 'FAIL'}")
    return ok


def test_regex_number():
    ok = True
    ok &= assert_score(score_regex_number, "answer is 42", {"expected": 42}, 1.0)
    ok &= assert_score(score_regex_number, "42", {"expected": 42}, 1.0)
    ok &= assert_score(score_regex_number, "5 then 10", {"expected": 10}, 1.0)  # last number wins
    ok &= assert_score(score_regex_number, "50%", {"expected": 50}, 1.0)  # percentage
    ok &= assert_score(score_regex_number, "50.4% approx 50", {"expected": 50}, 1.0)  # pct preferred
    ok &= assert_score(score_regex_number, "answer is 7", {"expected": 42}, 0.0)
    ok &= assert_score(score_regex_number, "no numbers", {"expected": 42}, 0.0)
    print(f"  regex_number: {'PASS' if ok else 'FAIL'}")
    return ok


def test_multiple_choice():
    ok = True
    ok &= assert_score(score_multiple_choice, "C", {"expected": "C"}, 1.0)
    ok &= assert_score(score_multiple_choice, "The answer is B", {"expected": "B"}, 1.0)
    ok &= assert_score(score_multiple_choice, "Among A, B, C, D, the answer is C",
                       {"expected": "C"}, 1.0)  # last match, not first
    ok &= assert_score(score_multiple_choice, "C", {"expected": "A"}, 0.0)
    ok &= assert_score(score_multiple_choice, "no letter", {"expected": "A"}, 0.0)
    print(f"  multiple_choice: {'PASS' if ok else 'FAIL'}")
    return ok


def test_code_exec_python():
    ok = True
    ok &= assert_score(score_code_exec_python,
                       "```python\nx = 42\n```",
                       {"tests": "assert x == 42"}, 1.0)
    ok &= assert_score(score_code_exec_python,
                       "```python\nx = 7\n```",
                       {"tests": "assert x == 42"}, 0.0)
    # _output injection (prose response, no code block)
    ok &= assert_score(score_code_exec_python,
                       "hello world",
                       {"tests": "assert 'hello' in _output"}, 1.0)
    # _output with code block — namespace injects _output
    ok &= assert_score(score_code_exec_python,
                       "```python\nx = 'hello world'\n```",
                       {"tests": "assert x == 'hello world'"}, 1.0)
    # multiple tests
    ok &= assert_score(score_code_exec_python,
                       "```python\nx = 2+2\n```",
                       {"tests": ["assert x == 4", "assert isinstance(x, int)"]}, 1.0)
    print(f"  code_exec_python: {'PASS' if ok else 'FAIL'}")
    return ok


def test_length_range():
    ok = True
    ok &= assert_score(score_length_range, "hello world",
                       {"min": 1, "max": 10, "unit": "words"}, 1.0)
    ok &= assert_score(score_length_range, "hello world",
                       {"min": 1, "max": 1, "unit": "words"}, 0.0)
    ok &= assert_score(score_length_range, "abc",
                       {"unit": "chars", "min": 3, "max": 3}, 1.0)
    ok &= assert_score(score_length_range, "line1\nline2\n",
                       {"unit": "lines", "min": 2, "max": 2}, 1.0)
    # sentences unit
    ok &= assert_score(score_length_range, "First. Second. Third.",
                       {"unit": "sentences", "min": 3, "max": 3}, 1.0)
    ok &= assert_score(score_length_range, "One sentence.",
                       {"unit": "sentences", "min": 1, "max": 1}, 1.0)
    ok &= assert_score(score_length_range, "A. B. C. D. E.",
                       {"unit": "sentences", "min": 5, "max": 5}, 1.0)
    print(f"  length_range: {'PASS' if ok else 'FAIL'}")
    return ok


def test_refusal():
    ok = True
    # must refuse
    ok &= assert_score(score_refusal, "I can't help with that.",
                       {"mode": "must_refuse"}, 1.0)
    ok &= assert_score(score_refusal, "Sure, here is how.",
                       {"mode": "must_refuse"}, 0.0)
    # must comply
    ok &= assert_score(score_refusal, "Here is the information.",
                       {"mode": "must_comply"}, 1.0)
    ok &= assert_score(score_refusal, "I'm not able to do that.",
                       {"mode": "must_comply"}, 0.0)
    # expanded signals
    ok &= assert_score(score_refusal, "I'd rather not do that.",
                       {"mode": "must_refuse"}, 1.0)
    ok &= assert_score(score_refusal, "I cannot provide that.",
                       {"mode": "must_refuse"}, 1.0)
    print(f"  refusal: {'PASS' if ok else 'FAIL'}")
    return ok


def test_json_schema():
    ok = True
    # legacy: simple key:type
    ok &= assert_score(score_json_schema,
                       '{"name": "test", "count": 42}',
                       {"schema": {"name": "str", "count": "int"}}, 1.0)
    ok &= assert_score(score_json_schema,
                       '{"name": "test"}',
                       {"required_keys": ["name", "missing"]}, 0.5)
    ok &= assert_score(score_json_schema,
                       "not json",
                       {"schema": {"name": "str"}}, 0.0)
    # extended: enum constraint (type passes, constraint fails → partial credit)
    ok &= assert_score(score_json_schema,
                       '{"status": "active"}',
                       {"schema": {"status": {"type": "str", "enum": ["active", "inactive"]}}}, 1.0)
    ok &= assert_score(score_json_schema,
                       '{"status": "unknown"}',
                       {"schema": {"status": {"type": "str", "enum": ["active", "inactive"]}}}, 0.5)
    # extended: minLength
    ok &= assert_score(score_json_schema,
                       '{"name": "hello"}',
                       {"schema": {"name": {"type": "str", "minLength": 3}}}, 1.0)
    ok &= assert_score(score_json_schema,
                       '{"name": "ab"}',
                       {"schema": {"name": {"type": "str", "minLength": 3}}}, 0.5)
    # extended: number range
    ok &= assert_score(score_json_schema,
                       '{"age": 25}',
                       {"schema": {"age": {"type": "int", "minimum": 0, "maximum": 150}}}, 1.0)
    ok &= assert_score(score_json_schema,
                       '{"age": -1}',
                       {"schema": {"age": {"type": "int", "minimum": 0}}}, 0.5)
    # extended: array with items
    ok &= assert_score(score_json_schema,
                       '{"tags": ["a", "b", "c"]}',
                       {"schema": {"tags": {"type": "list", "items": {"type": "str"}, "minItems": 1}}}, 1.0)
    ok &= assert_score(score_json_schema,
                       '{"tags": []}',
                       {"schema": {"tags": {"type": "list", "items": {"type": "str"}, "minItems": 1}}}, 0.5)
    # extended: nested dict
    ok &= assert_score(score_json_schema,
                       '{"config": {"host": "localhost", "port": 8080}}',
                       {"schema": {"config": {"type": "dict", "properties": {
                           "host": {"type": "str"},
                           "port": {"type": "int"}
                       }}}}, 1.0)
    ok &= assert_score(score_json_schema,
                        '{"config": {"host": "localhost"}}',
                        {"schema": {"config": {"type": "dict", "required": ["port"],
                            "properties": {"host": {"type": "str"}, "port": {"type": "int"}}}}}, 0.667)
    # standard JSON Schema format (properties/required at root)
    ok &= assert_score(score_json_schema,
                        '{"angle_degrees": 0.9, "shadow_cm": 28}',
                        {"schema": {"type": "object", "properties": {
                            "angle_degrees": {"type": "number"},
                            "shadow_cm": {"type": "integer"}
                        }, "required": ["angle_degrees", "shadow_cm"]}}, 1.0)
    ok &= assert_score(score_json_schema,
                        '{"angle_degrees": 0.9}',
                        {"schema": {"type": "object", "properties": {
                            "angle_degrees": {"type": "number"},
                            "shadow_cm": {"type": "integer"}
                        }, "required": ["angle_degrees", "shadow_cm"]}}, 0.5)
    ok &= assert_score(score_json_schema,
                        '{"angle_degrees": "0.9", "shadow_cm": 28}',
                        {"schema": {"type": "object", "properties": {
                            "angle_degrees": {"type": "number"},
                            "shadow_cm": {"type": "integer"}
                        }, "required": ["angle_degrees", "shadow_cm"]}}, 0.75)
    print(f"  json_schema: {'PASS' if ok else 'FAIL'}")
    return ok


def test_composite():
    ok = True
    # mode=all: returns min of parts if not all 1.0
    ok &= assert_score(score_composite,
                       "hello world",
                       {"mode": "all", "parts": [
                           {"type": "contains", "expected": "hello"},
                           {"type": "contains", "expected": "world"},
                       ]}, 1.0)
    ok &= assert_score(score_composite,
                       "hello world",
                       {"mode": "all", "parts": [
                           {"type": "contains", "expected": "hello"},
                           {"type": "contains", "expected": "missing"},
                       ]}, 0.0)
    # mode=mean
    ok &= assert_score(score_composite,
                       "hello world",
                       {"mode": "mean", "parts": [
                           {"type": "contains", "expected": "hello"},
                           {"type": "contains", "expected": "missing"},
                       ]}, 0.5)
    print(f"  composite: {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    results = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            results.append(fn())
    passed = sum(results)
    total = len(results)
    print(f"\n{'='*40}")
    print(f"Results: {passed}/{total} passed")
    if passed == total:
        print("All scorer tests PASSED")
    else:
        print(f"{total - passed} test(s) FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
