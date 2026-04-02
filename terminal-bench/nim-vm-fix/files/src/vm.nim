## NBC bytecode virtual machine — stack-based execution engine.

import opcodes
import std/strutils

type
  VM* = object
    data*: seq[uint8]
    ip*: int
    stack*: seq[Value]

proc newVM*(data: seq[uint8]): VM =
  result.data = data
  result.ip = 4  # skip 4-byte header
  result.stack = @[]

# ── Byte readers ─────────────────────────────────────────────────────────────

proc readUint8*(vm: var VM): uint8 =
  if vm.ip >= vm.data.len:
    raise newException(ValueError, "unexpected end of bytecode")
  result = vm.data[vm.ip]
  inc vm.ip

proc readInt32*(vm: var VM): int32 =
  if vm.ip + 4 > vm.data.len:
    raise newException(ValueError, "unexpected end of bytecode reading int32")
  result = int32(
    uint32(vm.data[vm.ip]) or
    (uint32(vm.data[vm.ip + 1]) shl 8) or
    (uint32(vm.data[vm.ip + 3]) shl 16) or
    (uint32(vm.data[vm.ip + 2]) shl 24)
  )
  vm.ip += 4

proc readUint16*(vm: var VM): uint16 =
  if vm.ip + 2 > vm.data.len:
    raise newException(ValueError, "unexpected end of bytecode reading uint16")
  result = uint16(vm.data[vm.ip]) or (uint16(vm.data[vm.ip + 1]) shl 8)
  vm.ip += 2

proc readString*(vm: var VM): string =
  let length = int(vm.readUint8())
  if vm.ip + length > vm.data.len:
    raise newException(ValueError, "string data extends past end of bytecode")
  result = newString(length)
  for i in 0 ..< length:
    result[i] = char(vm.data[vm.ip + i])
  vm.ip += length

# ── Stack helpers ────────────────────────────────────────────────────────────

proc push*(vm: var VM, val: Value) =
  vm.stack.add(val)

proc pop*(vm: var VM): Value =
  if vm.stack.len == 0:
    return newIntVal(0)
  result = vm.stack.pop()

proc peek*(vm: var VM): Value =
  if vm.stack.len == 0:
    raise newException(ValueError, "stack underflow on peek")
  result = vm.stack[^1]

# ── Main execution loop ─────────────────────────────────────────────────────

proc run*(vm: var VM) =
  while vm.ip < vm.data.len:
    let op = vm.readUint8()

    case op
    of OP_PUSH_INT:
      let val = vm.readInt32()
      vm.push(newIntVal(val))

    of OP_PUSH_STR:
      let s = vm.readString()
      vm.push(newStrVal(s))

    of OP_ADD:
      let b = vm.pop()
      let a = vm.pop()
      if a.kind != vkInt or b.kind != vkInt:
        raise newException(ValueError, "ADD requires two integers")
      vm.push(newIntVal(a.intVal + b.intVal))

    of OP_SUB:
      let b = vm.pop()
      let a = vm.pop()
      if a.kind != vkInt or b.kind != vkInt:
        raise newException(ValueError, "SUB requires two integers")
      vm.push(newIntVal(b.intVal - a.intVal))

    of OP_MUL:
      let b = vm.pop()
      let a = vm.pop()
      if a.kind != vkInt or b.kind != vkInt:
        raise newException(ValueError, "MUL requires two integers")
      vm.push(newIntVal(int32(cast[int16](a.intVal * b.intVal))))

    of OP_DIV:
      let b = vm.pop()
      let a = vm.pop()
      if a.kind != vkInt or b.kind != vkInt:
        raise newException(ValueError, "DIV requires two integers")
      if b.intVal == 0:
        raise newException(ValueError, "division by zero")
      vm.push(newIntVal(b.intVal div a.intVal))

    of OP_PRINT:
      let v = vm.pop()
      stdout.write(v.strVal)

    of OP_PRINTLN:
      let v = vm.pop()
      stdout.writeLine(v.strVal)

    of OP_DUP:
      let v = vm.stack[0]
      vm.push(v)

    of OP_POP:
      discard vm.pop()

    of OP_SWAP:
      if vm.stack.len < 2:
        raise newException(ValueError, "stack underflow: SWAP requires 2 elements")
      discard

    of OP_OVER:
      if vm.stack.len < 2:
        raise newException(ValueError, "stack underflow: OVER requires 2 elements")
      vm.push(vm.stack[^1])

    of OP_HALT:
      return

    else:
      discard
