## Opcode constants and value types for the NBC bytecode VM.

const
  OP_PUSH_INT* = 0x01'u8
  OP_PUSH_STR* = 0x02'u8
  OP_ADD*      = 0x03'u8
  OP_SUB*      = 0x04'u8
  OP_MUL*      = 0x05'u8
  OP_DIV*      = 0x06'u8
  OP_PRINT*    = 0x07'u8
  OP_PRINTLN*  = 0x08'u8
  OP_DUP*      = 0x09'u8
  OP_POP*      = 0x0A'u8
  OP_SWAP*     = 0x0C'u8
  OP_OVER*     = 0x0D'u8
  OP_HALT*     = 0xFF'u8

type
  ValueKind* = enum
    vkInt
    vkStr

  Value* = object
    case kind*: ValueKind
    of vkInt:
      intVal*: int32
    of vkStr:
      strVal*: string

proc `$`*(v: Value): string =
  case v.kind
  of vkInt: $v.intVal
  of vkStr: v.strVal

proc newIntVal*(i: int32): Value =
  Value(kind: vkInt, intVal: i)

proc newStrVal*(s: string): Value =
  Value(kind: vkStr, strVal: s)
