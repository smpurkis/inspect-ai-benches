"""Four-category public feedback for aligned resize behavior."""

import subprocess

BIN = "/tmp/aligned-pool"

subprocess.run(
    ["zig", "build-exe", "src/harness.zig", "-O", "ReleaseSafe", f"-femit-bin={BIN}"],
    cwd="/app/files",
    check=True,
)


def run(*commands):
    result = subprocess.run([BIN], input="\n".join(commands) + "\n", text=True,
                            capture_output=True, timeout=10, check=True)
    return result.stdout.splitlines()


def alloc_command(handle, command, *tail):
    return " ".join([command, *map(str, handle), *map(str, tail)])


def parsed(line):
    assert line.startswith("ok "), line
    return tuple(map(int, line.split()[1:]))


def test_normal_grow_moves_and_preserves_prefix():
    lines = run("alloc 16 8 37", "alloc 32 8 99")
    first, second = parsed(lines[0]), parsed(lines[1])
    commands = [
        "alloc 16 8 37", "alloc 32 8 99",
        alloc_command(first, "resize", 64, 64),
    ]
    moved = parsed(run(*commands)[2])
    assert moved[2] % 64 == 0 and moved[2] != first[2]
    assert run(*commands, alloc_command(moved, "check", 16, 37))[3] == "ok"
    assert second[2] != moved[2]


def test_edge_alignment_4096_and_overflow_failure_is_atomic():
    lines = run("alloc 19 4096 81")
    allocation = parsed(lines[0])
    assert allocation[2] % 4096 == 0
    commands = ["alloc 19 4096 81", alloc_command(allocation, "resize", 18446744073709551615, 4096)]
    result = run(*commands)
    assert result[1].startswith("err ")
    assert run(*commands, alloc_command(allocation, "check", 19, 81))[2] == "ok"


def test_invariant_shrink_preserves_and_move_stales_old_handle():
    old = parsed(run("alloc 100 16 123")[0])
    moved = parsed(run("alloc 100 16 123", alloc_command(old, "resize", 40, 256))[1])
    lines = run("alloc 100 16 123", alloc_command(old, "resize", 40, 256),
                alloc_command(moved, "check", 40, 123), alloc_command(old, "free"))
    assert lines[2] == "ok"
    assert lines[3] == "err InvalidHandle"


def test_deterministic_rerun_and_zero_free():
    script = ("alloc 7 32 4",)
    assert run(*script) == run(*script)
    allocation = parsed(run(*script)[0])
    lines = run(*script, alloc_command(allocation, "resize", 0, 32), alloc_command(allocation, "check", 1, 4))
    assert lines[1] == "nil"
    assert lines[2] == "err InvalidHandle"
