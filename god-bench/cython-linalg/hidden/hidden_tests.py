import importlib
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


FILES = Path("/app/files") if Path("/app/files").exists() else Path(__file__).resolve().parents[1] / "files"
KERNEL = FILES / "reorder_kernel.pxi"


@pytest.fixture(scope="session")
def module():
    if not list(FILES.glob("cylinalg*.so")):
        result = subprocess.run([sys.executable, "setup_build.py", "build_ext", "--inplace"], cwd=FILES, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stderr[-4000:]
    sys.path.insert(0, str(FILES))
    sys.modules.pop("cylinalg", None)
    return importlib.import_module("cylinalg")


def blocks(t):
    scale = max(1.0, float(np.max(np.abs(t), initial=0.0)))
    tolerance = 64 * np.finfo(float).eps * scale
    result = []
    index = 0
    while index < len(t):
        width = 2 if index + 1 < len(t) and abs(t[index + 1, index]) > tolerance else 1
        result.append((index, width))
        index += width
    return result


def selected_eigenvalues(t, select):
    values = []
    size = 0
    for start, width in blocks(t):
        if any(select[start:start + width]):
            values.extend(np.linalg.eigvals(t[start:start + width, start:start + width]))
            size += width
    return np.asarray(values, dtype=complex), size


def assert_multiset(actual, expected, tolerance=2e-8):
    remaining = list(np.asarray(actual, dtype=complex))
    for target in expected:
        position = min(range(len(remaining)), key=lambda i: abs(remaining[i] - target))
        assert abs(remaining.pop(position) - target) <= tolerance * max(1.0, abs(target))
    assert not remaining


def assert_ordered(t0, q0, select, t1, q1, atol=5e-10):
    t1 = np.asarray(t1)
    q1 = np.asarray(q1)
    n = len(t0)
    expected, leading = selected_eigenvalues(t0, select)
    assert t1.shape == (n, n) and q1.shape == (n, n)
    assert t1.dtype == np.float64 and q1.dtype == np.float64
    assert t1.flags.c_contiguous and q1.flags.c_contiguous
    assert np.all(np.isfinite(t1)) and np.all(np.isfinite(q1))
    np.testing.assert_allclose(q1.T @ q1, np.eye(n), atol=5e-11)
    np.testing.assert_allclose(q1 @ t1 @ q1.T, q0 @ t0 @ q0.T, atol=atol, rtol=2e-10)
    for row in range(2, n):
        np.testing.assert_allclose(t1[row, :row - 1], 0.0, atol=2e-11)
    if leading:
        assert_multiset(np.linalg.eigvals(t1[:leading, :leading]), expected)

    original_blocks = blocks(t0)
    expected_order = [
        block
        for selected in (True, False)
        for block in original_blocks
        if any(select[block[0]:block[0] + block[1]]) == selected
    ]
    reordered_blocks = blocks(t1)
    assert [width for _, width in reordered_blocks] == [width for _, width in expected_order]
    for (actual_start, width), (expected_start, _) in zip(reordered_blocks, expected_order):
        assert_multiset(
            np.linalg.eigvals(
                t1[actual_start:actual_start + width, actual_start:actual_start + width]
            ),
            np.linalg.eigvals(
                t0[expected_start:expected_start + width, expected_start:expected_start + width]
            ),
        )


def generated_case(seed, widths):
    rng = np.random.default_rng(seed)
    n = sum(widths)
    t = np.zeros((n, n), dtype=np.float64)
    cursor = 0
    for number, width in enumerate(widths):
        center = (-1.0 if number % 2 else 1.0) * (0.4 + number * 0.37)
        if width == 1:
            t[cursor, cursor] = center
        else:
            frequency = 0.15 + 0.03 * number
            t[cursor:cursor + 2, cursor:cursor + 2] = [[center, -frequency], [frequency, center]]
        cursor += width
    t += np.triu(rng.normal(scale=0.25, size=(n, n)), 1)
    # Restore the defining subdiagonal entries after adding upper couplings.
    cursor = 0
    for number, width in enumerate(widths):
        if width == 2:
            t[cursor + 1, cursor] = 0.15 + 0.03 * number
        cursor += width
    q, r = np.linalg.qr(rng.normal(size=(n, n)))
    q *= np.sign(np.diag(r))[None, :]
    return t, q


def test_inventory_source_policy_and_callsite():
    expected = {"TASK.md", "contract.toml", "cylinalg.pyx", "instructions.md", "reorder_kernel.pxi", "setup_build.py", "tests.py"}
    found = set()
    for path in FILES.rglob("*"):
        relative = path.relative_to(FILES)
        if relative.parts[0] in {"build", "__pycache__", ".pytest_cache"} or path.suffix in {".so", ".c", ".pyc"}:
            continue
        assert not path.is_symlink()
        if path.is_file():
            found.add(relative.as_posix())
    assert found == expected
    scaffold = (FILES / "cylinalg.pyx").read_text()
    assert 'include "reorder_kernel.pxi"' in scaffold and "_exchange_block" in scaffold
    source = KERNEL.read_text()
    assert 500 < len(source) < 24000
    for pattern in (r"^\s*(?:from|import)\s", r"\.\s*linalg\b", r"\bscipy\b", r"\b(?:ctypes|cffi|subprocess|importlib)\b", r"include_(?:bytes|str)"):
        assert re.search(pattern, source, re.MULTILINE | re.IGNORECASE) is None


@pytest.mark.parametrize(
    "seed,widths,selected_blocks",
    [
        (11, [1, 1, 1, 1], [3, 1]),
        (12, [2, 1, 2, 1], [2, 0]),
        (13, [1, 2, 2, 1, 1], [4, 1]),
        (14, [2, 2, 2, 2], [3, 1]),
        (15, [1, 1, 2, 1, 2, 1, 1], [6, 2, 0]),
    ],
)
def test_generated_mixed_blocks(module, seed, widths, selected_blocks):
    t, q = generated_case(seed, widths)
    selection = [False] * len(t)
    discovered = blocks(t)
    for block_index in selected_blocks:
        start, _ = discovered[block_index]
        selection[start] = True
    reordered = module.ordschur(t, q, selection)
    assert_ordered(t, q, selection, *reordered)


def test_conjugate_pair_member_metamorphism(module):
    t, q = generated_case(81, [1, 2, 1, 2])
    first = [False, True, False, False, False, False]
    second = [False, False, True, False, False, False]
    both = [False, True, True, False, False, False]
    outputs = [module.ordschur(t, q, select) for select in (first, second, both)]
    for output in outputs:
        assert_ordered(t, q, first, *output)
    np.testing.assert_array_equal(outputs[0][0], outputs[1][0])
    np.testing.assert_array_equal(outputs[0][0], outputs[2][0])
    np.testing.assert_array_equal(outputs[0][1], outputs[1][1])


def test_near_coincident_and_scale_metamorphism(module):
    t, q = generated_case(91, [1, 1, 2, 1, 2])
    t[0, 0] = 1.0
    t[1, 1] = 1.0 + 2e-13
    selection = [False, True, False, False, True, False, False]
    for factor in (1e-7, 1.0, 1e7):
        scaled = np.ascontiguousarray(t * factor)
        output = module.ordschur(scaled, q, selection)
        assert_ordered(scaled, q, selection, *output, atol=max(2e-12, factor * 2e-8))


def test_generated_single_mutation_and_determinism(module):
    t, q = generated_case(101, [2, 1, 1, 2, 1, 2, 1])
    for chosen in range(len(blocks(t))):
        selection = [False] * len(t)
        start, width = blocks(t)[chosen]
        selection[start + width - 1] = True
        first = module.ordschur(t, q, selection)
        second = module.ordschur(t, q, selection)
        assert_ordered(t, q, selection, *first)
        np.testing.assert_array_equal(first[0], second[0])
        np.testing.assert_array_equal(first[1], second[1])


def test_empty_all_and_orthogonal_similarity(module):
    t, q = generated_case(111, [1, 2, 1, 2, 1])
    for selection in ([False] * len(t), [True] * len(t)):
        output = module.ordschur(t, q, selection)
        assert_ordered(t, q, selection, *output)
    rng = np.random.default_rng(112)
    rotation, _ = np.linalg.qr(rng.normal(size=q.shape))
    selection = [False, False, False, True, False, False, True]
    output = module.ordschur(t, rotation @ q, selection)
    assert_ordered(t, rotation @ q, selection, *output)


def test_adversarial_validation(module):
    eye = np.eye(3)
    bad_cases = [
        (np.ones((2, 3)), np.eye(2), [True, False]),
        (eye, np.eye(2), [True] * 3),
        (eye.astype(np.float32), eye, [True] * 3),
        (eye, eye, [True, False]),
        (np.array([[1.0, 0, 0], [0, 2, 0], [1e-3, 0, 3.0]]), eye, [False] * 3),
        (eye, np.array([[1.0, 0, 0], [0, 2.0, 0], [0, 0, 1.0]]), [False] * 3),
        (np.array([[np.nan]]), np.eye(1), [True]),
    ]
    for t, q, selection in bad_cases:
        with pytest.raises(ValueError):
            module.ordschur(t, q, selection)


if __name__ == "__main__":
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
