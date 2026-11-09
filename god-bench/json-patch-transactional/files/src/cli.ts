declare function require(name: string): any;
declare const process: any;

import { applyOperation } from "./applyOperation";
import { JsonValue, Operation } from "./types";

const readline = require("readline");
const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
lines.on("line", (line: string) => {
  const request = JSON.parse(line) as { document: JsonValue; operation: Operation };
  try {
    const result = applyOperation(request.document, request.operation);
    process.stdout.write(JSON.stringify({ ok: true, result }) + "\n");
  } catch (error) {
    process.stdout.write(JSON.stringify({
      ok: false,
      document: request.document,
      error: error instanceof Error ? error.name : "unknown",
    }) + "\n");
  }
});
