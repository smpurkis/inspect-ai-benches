## Bytecode file loader — validates the NBC header and returns raw bytes.

import opcodes

const
  MAGIC_0 = 0x4E'u8  # 'N'
  MAGIC_1 = 0x42'u8  # 'B'
  MAGIC_2 = 0x43'u8  # 'C'
  MAGIC_3 = 0x01'u8  # version

proc loadBytecode*(filename: string): seq[uint8] =
  ## Read an .nbc file and validate its 4-byte magic header.
  ## Returns the full file contents (header + instructions).
  let f = open(filename, fmRead)
  defer: f.close()
  let size = f.getFileSize()
  if size < 4:
    raise newException(ValueError, "file too short: missing NBC header")

  var data = newSeq[uint8](size)
  let bytesRead = f.readBytes(data, 0, size)
  if bytesRead != size:
    raise newException(IOError, "failed to read complete file")

  if data[0] != MAGIC_3 or data[1] != MAGIC_2 or data[2] != MAGIC_1:
    raise newException(ValueError,
      "invalid magic: expected NBC header, got [" &
      $data[0] & ", " & $data[1] & ", " & $data[2] & ", " & $data[3] & "]")

  return data
