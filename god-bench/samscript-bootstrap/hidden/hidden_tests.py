import importlib
import inspect
import random
import re
import sys
import tomllib
from pathlib import Path

FILES = Path("/app/files") if Path("/app/files").exists() else Path(__file__).parents[1] / "files"
sys.path.insert(0, str(FILES))
from scaffold import Parser, RuntimeFault, load_program, run_source
from runtime import Runtime


def triangular_without(values, skipped):
    return sum(value for value in values if value not in skipped)


def generated_program(seed, limit, skip, stop):
    rng = random.Random(seed)
    pad = rng.randint(3, 19)
    source = f"""
        fn worker(limit) {{
            let i = 0; let total = {pad};
            loop {{
                i += 1;
                if i == {skip} {{ continue; }}
                if i > {stop} {{ break; }}
                if i < limit {{ total += i; }}
            }}
            return total;
            total = 999999;
        }}
        fn main() {{ print(worker({limit})); }}
    """
    expected = pad + triangular_without(range(1, min(limit - 1, stop) + 1), {skip})
    return source, f"{expected}\n"


def test_generated_scope_and_control_oracle():
    for index in range(24):
        source, expected = generated_program(0xB0057 + index, 5 + index % 7, 1 + index % 4, 7 + index % 5)
        assert run_source(source) == expected


def test_metamorphic_alpha_rename_and_dead_branch():
    source, expected = generated_program(91, 9, 3, 12)
    renamed = re.sub(r"\btotal\b", "accumulator", source)
    renamed = re.sub(r"\bi\b", "cursor", renamed)
    transformed = renamed.replace("fn main() {", "fn main() { if false { let hidden = 8; print(hidden); }")
    assert run_source(source) == run_source(transformed) == expected


def test_recursive_frames_do_not_leak_bindings():
    source = """
        fn sum(n) { if n == 0 { return 0; } let saved = n; return saved + sum(n - 1); }
        fn main() { let saved = 40; print(sum(12)); print(saved); }
    """
    assert run_source(source) == "78\n40\n"


def test_supplied_import_loader_reaches_candidate_runtime(tmp_path):
    (tmp_path / "math.sam").write_text("fn twice(x) { return x * 2; }")
    main = tmp_path / "main.sam"
    main.write_text('from "math.sam" import twice;\nfn main() { print(twice(17)); }')
    output = []
    Runtime(load_program(main), output).run()
    assert output == ["34"]


def test_scope_unwinds_after_continue_and_break():
    source = """
        fn main() { let i = 0; loop { i += 1; if i == 1 { let leaked = 2; continue; }
        if i == 2 { let leaked = 3; break; } } print(i); }
    """
    assert run_source(source) == "2\n"
    with __import__("pytest").raises(RuntimeFault, match="undefined"):
        run_source(source.replace("print(i)", "print(leaked)"))


def test_single_literal_mutation_is_observable():
    first, expected_first = generated_program(177, 10, 4, 11)
    second, expected_second = generated_program(177, 11, 4, 11)
    assert expected_first != expected_second
    assert run_source(first) == expected_first
    assert run_source(second) == expected_second


def test_structural_reachability_of_every_kernel_hook():
    class Traced(Runtime):
        hits = set()

        def __getattribute__(self, name):
            if name in {"declare", "lookup", "assign", "execute_block", "execute_statement", "invoke"}:
                type(self).hits.add(name)
            return super().__getattribute__(name)

    scaffold = importlib.import_module("scaffold")
    functions = Parser("fn id(x) { let y = x; y += 1; return y; } fn main() { print(id(4)); }").program()
    output = []
    Traced(functions, output).run()
    assert output == ["5"]
    assert Traced.hits == {"declare", "lookup", "assign", "execute_block", "execute_statement", "invoke"}
    assert "execute_statement" in inspect.getsource(Runtime.execute_block)


def test_artifact_and_policy_are_synchronized():
    contract = tomllib.loads((FILES / "contract.toml").read_text())
    assert contract["policy"]["editable"] == ["runtime.py"]
    assert contract["limits"]["max_model_tokens"] == 96000
    assert contract["limits"]["wall_clock_seconds"] == 43200
    assert not (FILES / "runtime.py").is_symlink()
    allowed = {"runtime.py", "scaffold.py", "tests.py"}
    assert {path.name for path in FILES.glob("*.py")} == allowed
