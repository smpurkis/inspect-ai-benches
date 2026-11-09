import { addAt, parsePointer, readAt, removeAt } from "./pointer";
import { JsonValue, Operation } from "./types";

export function applyOperation(document: JsonValue, operation: Operation): JsonValue {
  const from = parsePointer(operation.from);
  const path = parsePointer(operation.path);

  if (operation.op === "copy") {
    // BUG: containers are shared with the source instead of deeply copied.
    return addAt(document, path, readAt(document, from));
  }

  // BUG: a failed add leaves the source removed and descendants are unchecked.
  const [root, value] = removeAt(document, from);
  return addAt(root, path, value);
}
