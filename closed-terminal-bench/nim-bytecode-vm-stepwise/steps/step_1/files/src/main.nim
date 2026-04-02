## NBC bytecode VM — command-line entry point.

import os
import parser
import vm as vmmod

proc main() =
  # BUG: does not check whether the user supplied a filename argument.
  # Accessing paramStr(1) with no arguments raises an IndexDefect.
  let filename = paramStr(1)

  let data = loadBytecode(filename)
  var machine = newVM(data)
  machine.run()

main()
