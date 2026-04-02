## NBC bytecode VM — command-line entry point.

import os
import parser
import vm as vmmod

proc main() =
  let filename = paramStr(1)

  let data = loadBytecode(filename)
  var machine = newVM(data)
  machine.run()

main()
