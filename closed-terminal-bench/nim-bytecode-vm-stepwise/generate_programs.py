#!/usr/bin/env python3
"""Generate .nbc bytecode programs and expected outputs for nim-bytecode-vm-stepwise."""

import struct
from pathlib import Path

BASE = Path(__file__).parent

# ── Bytecode instruction builders ───────────────────────────────────────────

def header():      return b"NBC\x01"
def push_int(v):   return b"\x01" + struct.pack("<i", v)
def push_str(s):
    enc = s.encode("utf-8")
    return b"\x02" + struct.pack("<H", len(enc)) + enc
def op_add():      return b"\x03"
def op_sub():      return b"\x04"
def op_mul():      return b"\x05"
def op_div():      return b"\x06"
def op_print():    return b"\x07"
def op_println():  return b"\x08"
def op_dup():      return b"\x09"
def op_pop():      return b"\x0a"
def op_mod():      return b"\x0b"
def op_swap():     return b"\x0c"
def op_over():     return b"\x0d"
def op_jmp(off):   return b"\x10" + struct.pack("<H", off)
def op_jz(off):    return b"\x11" + struct.pack("<H", off)
def op_jnz(off):   return b"\x12" + struct.pack("<H", off)
def op_cmp_lt():   return b"\x13"
def op_cmp_eq():   return b"\x14"
def op_cmp_gt():   return b"\x15"
def op_fwrite(path):
    enc = path.encode("utf-8")
    return b"\x20" + struct.pack("<H", len(enc)) + enc
def op_fread(path):
    enc = path.encode("utf-8")
    return b"\x21" + struct.pack("<H", len(enc)) + enc
def op_halt():     return b"\xff"


# ── Tiny reference VM (Python) for computing expected outputs ───────────────

OPNAMES = {
    0x01: "PUSH_INT", 0x02: "PUSH_STR",
    0x03: "ADD", 0x04: "SUB", 0x05: "MUL", 0x06: "DIV",
    0x07: "PRINT", 0x08: "PRINTLN",
    0x09: "DUP", 0x0A: "POP", 0x0B: "MOD",
    0x0C: "SWAP", 0x0D: "OVER",
    0x10: "JMP", 0x11: "JZ", 0x12: "JNZ",
    0x13: "CMP_LT", 0x14: "CMP_EQ", 0x15: "CMP_GT",
    0x20: "FWRITE", 0x21: "FREAD",
    0xFF: "HALT",
}

class MiniVM:
    def __init__(self, data: bytes):
        self.data = data
        self.ip = 4
        self.stack: list = []
        self.output = ""
        self.trace_lines: list[str] = []
        self.step = 0
        self.files: dict[str, str] = {}
        self.error: str | None = None

    # ── byte readers ──
    def _u8(self):
        v = self.data[self.ip]; self.ip += 1; return v

    def _i32(self):
        v = struct.unpack_from("<i", self.data, self.ip)[0]; self.ip += 4; return v

    def _u16(self):
        v = struct.unpack_from("<H", self.data, self.ip)[0]; self.ip += 2; return v

    def _str(self):
        n = self._u16()
        s = self.data[self.ip : self.ip + n].decode("utf-8"); self.ip += n; return s

    def _path(self):
        return self._str()

    # ── helpers ──
    def _fmt_stack(self):
        parts = []
        for v in self.stack:
            parts.append(f'"{v}"' if isinstance(v, str) else str(v))
        return "[" + ", ".join(parts) + "]"

    def _trace(self, ip, name, args=""):
        self.step += 1
        line = f"[{self.step:04d}] {ip:04x}: {name}"
        if args:
            line += f" {args}"
        line += f" | stack: {self._fmt_stack()}"
        self.trace_lines.append(line)

    def _pop(self):
        return self.stack.pop()

    # ── run ──
    def run(self, trace=False):
        try:
            self._exec(trace)
        except Exception as exc:
            self.error = str(exc)

    def _exec(self, trace):
        while self.ip < len(self.data):
            iip = self.ip
            op = self._u8()

            if op == 0x01:
                v = self._i32(); self.stack.append(v)
                if trace: self._trace(iip, "PUSH_INT", str(v))
            elif op == 0x02:
                s = self._str(); self.stack.append(s)
                if trace: self._trace(iip, "PUSH_STR", f'"{s}"')
            elif op == 0x03:
                b, a = self._pop(), self._pop()
                self.stack.append(a + b)
                if trace: self._trace(iip, "ADD")
            elif op == 0x04:
                b, a = self._pop(), self._pop()
                self.stack.append(a - b)
                if trace: self._trace(iip, "SUB")
            elif op == 0x05:
                b, a = self._pop(), self._pop()
                self.stack.append(a * b)
                if trace: self._trace(iip, "MUL")
            elif op == 0x06:
                b, a = self._pop(), self._pop()
                if b == 0: raise RuntimeError("division by zero")
                self.stack.append(int(a / b) if a * b < 0 else a // b)
                if trace: self._trace(iip, "DIV")
            elif op == 0x07:
                v = self._pop(); self.output += str(v)
                if trace: self._trace(iip, "PRINT")
            elif op == 0x08:
                v = self._pop(); self.output += str(v) + "\n"
                if trace: self._trace(iip, "PRINTLN")
            elif op == 0x09:
                self.stack.append(self.stack[-1])
                if trace: self._trace(iip, "DUP")
            elif op == 0x0A:
                self._pop()
                if trace: self._trace(iip, "POP")
            elif op == 0x0B:
                b, a = self._pop(), self._pop()
                self.stack.append(a % b)
                if trace: self._trace(iip, "MOD")
            elif op == 0x0C:
                self.stack[-1], self.stack[-2] = self.stack[-2], self.stack[-1]
                if trace: self._trace(iip, "SWAP")
            elif op == 0x0D:
                self.stack.append(self.stack[-2])
                if trace: self._trace(iip, "OVER")
            elif op == 0x10:
                t = self._u16()
                if trace: self._trace(iip, "JMP", f"{t:04x}")
                self.ip = t
            elif op == 0x11:
                t = self._u16(); v = self._pop()
                if trace: self._trace(iip, "JZ", f"{t:04x}")
                if v == 0: self.ip = t
            elif op == 0x12:
                t = self._u16(); v = self._pop()
                if trace: self._trace(iip, "JNZ", f"{t:04x}")
                if v != 0: self.ip = t
            elif op == 0x13:
                b, a = self._pop(), self._pop()
                self.stack.append(1 if a < b else 0)
                if trace: self._trace(iip, "CMP_LT")
            elif op == 0x14:
                b, a = self._pop(), self._pop()
                self.stack.append(1 if a == b else 0)
                if trace: self._trace(iip, "CMP_EQ")
            elif op == 0x15:
                b, a = self._pop(), self._pop()
                self.stack.append(1 if a > b else 0)
                if trace: self._trace(iip, "CMP_GT")
            elif op == 0x20:
                p = self._path(); v = self._pop()
                self.files[p] = str(v)
                if trace: self._trace(iip, "FWRITE", f'"{p}"')
            elif op == 0x21:
                p = self._path()
                self.stack.append(self.files.get(p, ""))
                if trace: self._trace(iip, "FREAD", f'"{p}"')
            elif op == 0xFF:
                if trace: self._trace(iip, "HALT")
                return
            else:
                raise RuntimeError(f"unknown opcode 0x{op:02x}")


def verify_and_write(name: str, data: bytes, out_dir: Path,
                     expected_out: str | None, trace_dir: Path | None = None):
    """Write .nbc file, run mini-VM, verify expected output, write expected files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    nbc_path = out_dir / f"{name}.nbc"
    nbc_path.write_bytes(data)

    # Run VM
    vm = MiniVM(data)
    vm.run(trace=False)
    if expected_out is not None:
        assert vm.error is None, f"{name}: VM error: {vm.error}"
        assert vm.output == expected_out, (
            f"{name}: output mismatch.\n  Got:    {vm.output!r}\n  Expect: {expected_out!r}"
        )
        # Write expected output
        exp_name = f"expected_{name.replace('.nbc', '')}.txt"
        (out_dir / exp_name).write_text(expected_out)

    # Generate trace if requested
    if trace_dir is not None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_nbc = trace_dir / f"trace_{name}.nbc" if not name.startswith("trace_") else trace_dir / f"{name}.nbc"
        trace_nbc.write_bytes(data)
        tvm = MiniVM(data)
        tvm.run(trace=True)
        trace_name = f"expected_trace_{name}.txt" if not name.startswith("trace_") else f"expected_{name}.txt"
        (trace_dir / trace_name).write_text("\n".join(tvm.trace_lines) + "\n" if tvm.trace_lines else "")

    print(f"  {name}: OK ({len(data)} bytes)")


def build_loop_sum(n: int) -> bytes:
    """Build a sum-from-1-to-n loop program: PUSH 0, PUSH n, loop(SWAP OVER ADD SWAP PUSH1 SUB DUP JNZ), POP PRINTLN HALT."""
    hdr = header()
    pre = push_int(0) + push_int(n)
    loop_start = len(hdr) + len(pre)
    loop_body = (op_swap() + op_over() + op_add() + op_swap() +
                 push_int(1) + op_sub() + op_dup())
    # JNZ placeholder — target = loop_start
    loop_body += op_jnz(loop_start)
    post = op_pop() + op_println() + op_halt()
    return hdr + pre + loop_body + post


def build_countdown(n: int) -> bytes:
    """Countdown from n to 1, printing each."""
    hdr = header()
    pre = push_int(n)
    loop_start = len(hdr) + len(pre)
    loop_body = op_dup() + op_println() + push_int(1) + op_sub() + op_dup()
    loop_body += op_jnz(loop_start)
    post = op_pop() + op_halt()
    return hdr + pre + loop_body + post


# ── Program definitions ─────────────────────────────────────────────────────

def generate_all():
    s1f = BASE / "steps/step_1/files/programs"
    s1h = BASE / "steps/step_1/hidden/programs"
    s2f = BASE / "steps/step_2/files/programs"
    s2h = BASE / "steps/step_2/hidden/programs"
    s3f = BASE / "steps/step_3/files/programs"
    s3h = BASE / "steps/step_3/hidden/programs"

    print("Step 1 visible:")
    # hello.nbc
    hello_data = header() + push_str("Hello, World!") + op_println() + op_halt()
    verify_and_write("hello", hello_data, s1f, "Hello, World!\n")

    # arithmetic.nbc  (2 + 3*4 = 14)
    arith_data = (header() + push_int(2) + push_int(3) + push_int(4) +
                  op_mul() + op_add() + op_println() + op_halt())
    verify_and_write("arithmetic", arith_data, s1f, "14\n")

    print("Step 1 hidden:")
    # fibonacci.nbc — first 10 fib numbers
    fibs = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]
    fib_body = header()
    for f in fibs:
        fib_body += push_int(f) + op_println()
    fib_body += op_halt()
    verify_and_write("fibonacci", fib_body, s1h, "".join(f"{f}\n" for f in fibs))

    # nested_arithmetic.nbc  (10 - 3) * 2 + 1 = 15
    nested_data = (header() + push_int(10) + push_int(3) + op_sub() +
                   push_int(2) + op_mul() + push_int(1) + op_add() +
                   op_println() + op_halt())
    verify_and_write("nested_arithmetic", nested_data, s1h, "15\n")

    # strings.nbc — concatenated print
    strings_data = (header() + push_str("foo") + op_print() +
                    push_str("bar") + op_println() + op_halt())
    verify_and_write("strings", strings_data, s1h, "foobar\n")

    # empty.nbc — just halt
    empty_data = header() + op_halt()
    verify_and_write("empty", empty_data, s1h, "")

    # ── Step 2 visible ──
    print("Step 2 visible:")

    # branch_simple.nbc — if 1 then "yes" else "no"
    hdr = header()
    p = len(hdr)
    part_push1 = push_int(1)                  # 5 bytes
    p += len(part_push1)
    part_jz = op_jz(0)                         # placeholder, 3 bytes
    p += len(part_jz)
    part_yes = push_str("yes")                 # 6 bytes
    p += len(part_yes)
    part_println1 = op_println()               # 1 byte
    p += len(part_println1)
    part_jmp = op_jmp(0)                       # placeholder, 3 bytes
    p += len(part_jmp)
    else_offset = p
    part_no = push_str("no")                   # 5 bytes
    p += len(part_no)
    part_println2 = op_println()               # 1 byte
    p += len(part_println2)
    end_offset = p
    # Patch offsets
    part_jz = op_jz(else_offset)
    part_jmp = op_jmp(end_offset)
    branch_data = (hdr + part_push1 + part_jz + part_yes + part_println1 +
                   part_jmp + part_no + part_println2 + op_halt())
    verify_and_write("branch_simple", branch_data, s2f, "yes\n")

    # loop_sum.nbc — sum 1..5 = 15
    loop5_data = build_loop_sum(5)
    verify_and_write("loop_sum", loop5_data, s2f, "15\n")

    # comparisons.nbc — CMP_LT, CMP_EQ, CMP_GT for (3,5)
    cmp_data = (header() +
                push_int(3) + push_int(5) + op_cmp_lt() + op_println() +
                push_int(3) + push_int(5) + op_cmp_eq() + op_println() +
                push_int(3) + push_int(5) + op_cmp_gt() + op_println() +
                op_halt())
    verify_and_write("comparisons", cmp_data, s2f, "1\n0\n0\n")

    # file_write.nbc — write string to file
    fw_data = (header() + push_str("hello from nbc") +
               op_fwrite("/tmp/nbc_output.txt") + op_halt())
    s2f.mkdir(parents=True, exist_ok=True)
    (s2f / "file_write.nbc").write_bytes(fw_data)
    # No stdout expected; test checks file existence
    vm = MiniVM(fw_data)
    vm.run()
    assert vm.error is None
    assert vm.output == ""
    assert vm.files.get("/tmp/nbc_output.txt") == "hello from nbc"
    print(f"  file_write: OK ({len(fw_data)} bytes)")

    # ── Step 2 hidden ──
    print("Step 2 hidden:")

    # nested_branch.nbc — if 1 then (if 0 then "inner-yes" else "inner-no") else "outer-no"
    hdr = header()
    parts = []
    pos = len(hdr)

    def emit(b):
        nonlocal pos
        parts.append(b)
        pos += len(b)
        return len(b)

    emit(push_int(1))
    jz_outer_idx = len(parts); emit(op_jz(0))   # placeholder
    emit(push_int(0))
    jz_inner_idx = len(parts); emit(op_jz(0))   # placeholder
    emit(push_str("inner-yes"))
    emit(op_println())
    jmp_end_1_idx = len(parts); emit(op_jmp(0)) # placeholder
    inner_no_pos = pos
    emit(push_str("inner-no"))
    emit(op_println())
    jmp_end_2_idx = len(parts); emit(op_jmp(0)) # placeholder
    outer_no_pos = pos
    emit(push_str("outer-no"))
    emit(op_println())
    end_pos = pos
    emit(op_halt())

    # Patch jumps
    parts[jz_outer_idx] = op_jz(outer_no_pos)
    parts[jz_inner_idx] = op_jz(inner_no_pos)
    parts[jmp_end_1_idx] = op_jmp(end_pos)
    parts[jmp_end_2_idx] = op_jmp(end_pos)
    nested_branch_data = hdr + b"".join(parts)
    verify_and_write("nested_branch", nested_branch_data, s2h, "inner-no\n")

    # loop_100.nbc — sum 1..100 = 5050
    loop100_data = build_loop_sum(100)
    verify_and_write("loop_100", loop100_data, s2h, "5050\n")

    # file_read.nbc — write then read back
    fr_data = (header() + push_str("test content") +
               op_fwrite("/tmp/nbc_read_test.txt") +
               op_fread("/tmp/nbc_read_test.txt") +
               op_println() + op_halt())
    verify_and_write("file_read", fr_data, s2h, "test content\n")

    # div_zero.nbc — should error
    dz_data = header() + push_int(10) + push_int(0) + op_div() + op_halt()
    s2h.mkdir(parents=True, exist_ok=True)
    (s2h / "div_zero.nbc").write_bytes(dz_data)
    vm = MiniVM(dz_data); vm.run()
    assert vm.error is not None
    print(f"  div_zero: OK (error expected, {len(dz_data)} bytes)")

    # jump_oob.nbc — jump out of bounds
    joob_data = header() + op_jmp(9999) + op_halt()
    (s2h / "jump_oob.nbc").write_bytes(joob_data)
    print(f"  jump_oob: OK ({len(joob_data)} bytes)")

    # type_mismatch.nbc — add string + int
    tm_data = header() + push_str("hello") + push_int(5) + op_add() + op_halt()
    (s2h / "type_mismatch.nbc").write_bytes(tm_data)
    print(f"  type_mismatch: OK ({len(tm_data)} bytes)")

    # ── Step 3 ──
    print("Step 3 visible:")

    # trace_hello.nbc — same as hello, with expected trace
    tvm = MiniVM(hello_data); tvm.run(trace=True)
    s3f.mkdir(parents=True, exist_ok=True)
    (s3f / "trace_hello.nbc").write_bytes(hello_data)
    (s3f / "expected_trace_hello.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_hello: OK (trace {len(tvm.trace_lines)} lines)")

    print("Step 3 hidden:")

    # trace_branch.nbc
    tvm = MiniVM(branch_data); tvm.run(trace=True)
    s3h.mkdir(parents=True, exist_ok=True)
    (s3h / "trace_branch.nbc").write_bytes(branch_data)
    (s3h / "expected_trace_branch.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_branch: OK (trace {len(tvm.trace_lines)} lines)")

    # trace_loop.nbc — countdown from 3
    countdown3 = build_countdown(3)
    tvm = MiniVM(countdown3); tvm.run(trace=True)
    assert tvm.error is None
    (s3h / "trace_loop.nbc").write_bytes(countdown3)
    (s3h / "expected_trace_loop.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_loop: OK (trace {len(tvm.trace_lines)} lines)")

    # trace_large.nbc — countdown from 10
    countdown10 = build_countdown(10)
    tvm = MiniVM(countdown10); tvm.run(trace=True)
    assert tvm.error is None
    (s3h / "trace_large.nbc").write_bytes(countdown10)
    (s3h / "expected_trace_large.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_large: OK (trace {len(tvm.trace_lines)} lines)")

    # trace_error.nbc — div by zero, trace should record up to the error
    tvm = MiniVM(dz_data); tvm.run(trace=True)
    (s3h / "trace_error.nbc").write_bytes(dz_data)
    (s3h / "expected_trace_error.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_error: OK (trace {len(tvm.trace_lines)} lines, error expected)")

    # trace_fileio.nbc — write + read with trace
    fio_data = (header() + push_str("traced data") +
                op_fwrite("/tmp/trace_io.txt") +
                op_fread("/tmp/trace_io.txt") +
                op_println() + op_halt())
    tvm = MiniVM(fio_data); tvm.run(trace=True)
    assert tvm.error is None
    (s3h / "trace_fileio.nbc").write_bytes(fio_data)
    (s3h / "expected_trace_fileio.txt").write_text("\n".join(tvm.trace_lines) + "\n")
    print(f"  trace_fileio: OK (trace {len(tvm.trace_lines)} lines)")

    print("\nAll programs generated successfully.")


if __name__ == "__main__":
    generate_all()
