"""Generated operation traces and allocator metamorphisms."""

import random
import subprocess

import pytest

BIN = "/tmp/aligned-pool"


def command(name, handle, *args):
    return " ".join([name, *map(str, handle), *map(str, args)])


def execute(commands):
    result = subprocess.run([BIN], input="\n".join(commands) + "\n", text=True,
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def allocation(line):
    assert line.startswith("ok "), line
    return tuple(map(int, line.split()[1:]))


@pytest.mark.parametrize("alignment", [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096])
def test_every_alignment_and_forced_move_preserves(alignment):
    initial = execute(["alloc 73 1 173", "alloc 257 1 29"])
    old = allocation(initial[0])
    commands = ["alloc 73 1 173", "alloc 257 1 29", command("resize", old, 311, alignment)]
    lines = execute(commands)
    new = allocation(lines[2])
    assert new[2] % alignment == 0
    checked = execute(commands + [command("check", new, 73, 173), command("check", old, 1, 173)])
    assert checked[3] == "ok"
    assert checked[4] == "err InvalidHandle"


@pytest.mark.parametrize("seed", range(10))
def test_generated_allocate_resize_free_sequences(seed):
    rng = random.Random(0xA110C + seed)
    commands = []
    expected = []
    live = []
    for step in range(45):
        if not live or rng.random() < .45:
            size = rng.randrange(1, 700)
            align = 1 << rng.randrange(0, 10)
            value = rng.randrange(1, 256)
            commands.append(f"alloc {size} {align} {value}")
            lines = execute(commands)
            handle = allocation(lines[-1])
            assert handle[2] % align == 0
            live.append((handle, value, size))
        elif rng.random() < .7:
            index = rng.randrange(len(live))
            old, value, known_prefix = live[index]
            new_size = rng.randrange(1, 1000)
            align = 1 << rng.randrange(0, 13)
            commands.append(command("resize", old, new_size, align))
            lines = execute(commands)
            new = allocation(lines[-1])
            assert new[2] % align == 0
            known_prefix = min(known_prefix, new_size)
            commands.append(command("check", new, known_prefix, value))
            assert execute(commands)[-1] == "ok"
            live[index] = (new, value, known_prefix)
        else:
            index = rng.randrange(len(live))
            old, _, _ = live.pop(index)
            commands.append(command("free", old))
            assert execute(commands)[-1] == "ok"


def test_failure_atomicity_overflow_invalid_alignment_and_oom():
    old = allocation(execute(["alloc 101 64 211"])[0])
    bad_requests = [
        command("resize", old, 18446744073709551615, 64),
        command("resize", old, 200, 3),
        command("resize", old, 200, 8192),
        command("resize", old, 200000, 64),
    ]
    for request in bad_requests:
        lines = execute(["alloc 101 64 211", request, command("check", old, 101, 211)])
        assert lines[1].startswith("err ")
        assert lines[2] == "ok"


def test_coalesced_space_reused_and_stale_slot_generation_rejected():
    first_lines = execute(["alloc 100 1 1", "alloc 100 1 2", "alloc 100 1 3"])
    a, b, c = map(allocation, first_lines)
    commands = ["alloc 100 1 1", "alloc 100 1 2", "alloc 100 1 3",
                command("free", a), command("free", b), "alloc 180 64 9"]
    lines = execute(commands)
    merged = allocation(lines[-1])
    assert merged[2] == 0
    assert merged[0] in (a[0], b[0]) and merged[1] != a[1]
    stale = execute(commands + [command("free", a), command("check", b, 1, 2), command("check", c, 100, 3)])
    assert stale[-3] == "err InvalidHandle"
    assert stale[-2] == "err InvalidHandle"
    assert stale[-1] == "ok"


def test_metamorphic_unrelated_tail_allocation_does_not_change_in_place_resize():
    base = execute(["alloc 64 64 44"])
    old = allocation(base[0])
    grown_base = allocation(execute(["alloc 64 64 44", command("resize", old, 96, 64)])[1])
    grown_with_tail = allocation(execute([
        "alloc 64 64 44", "alloc 64 64 77", command("free", allocation(execute(["alloc 64 64 44", "alloc 64 64 77"])[1])),
        command("resize", old, 96, 64),
    ])[-1])
    assert grown_base[:3] == grown_with_tail[:3]


def test_kernel_reachability_resize_zero_and_forged_handles():
    old = allocation(execute(["alloc 8 8 5"])[0])
    forged = (old[0], old[1], old[2] + 1, old[3], old[4])
    lines = execute(["alloc 8 8 5", command("resize", forged, 4, 8),
                     command("resize", old, 0, 8), command("check", old, 1, 5)])
    assert lines[1] == "err InvalidHandle"
    assert lines[2] == "nil"
    assert lines[3] == "err InvalidHandle"


def test_complete_handle_is_validated_before_alignment():
    old = allocation(execute(["alloc 8 8 5"])[0])
    forged_handles = [
        (old[0] + 128, *old[1:]),
        (old[0], old[1] + 1, *old[2:]),
        (*old[:2], old[2] + 1, *old[3:]),
        (*old[:3], old[3] + 1, old[4]),
        (*old[:4], old[4] * 2),
    ]
    lines = execute(
        ["alloc 8 8 5"]
        + [command("resize", forged, 16, 3) for forged in forged_handles]
    )
    assert lines[1:] == ["err InvalidHandle"] * len(forged_handles)
