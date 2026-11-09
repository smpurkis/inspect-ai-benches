import { JsonValue, PatchError } from "./types";

export function parsePointer(pointer: string): string[] {
  if (pointer === "") return [];
  if (!pointer.startsWith("/")) throw new PatchError("pointer must start with /");
  return pointer.slice(1).split("/").map((token) => {
    let decoded = "";
    for (let i = 0; i < token.length; i++) {
      if (token[i] !== "~") {
        decoded += token[i];
      } else if (token[i + 1] === "0") {
        decoded += "~";
        i++;
      } else if (token[i + 1] === "1") {
        decoded += "/";
        i++;
      } else {
        throw new PatchError("invalid pointer escape");
      }
    }
    return decoded;
  });
}

function arrayIndex(token: string, length: number, allowEnd: boolean): number {
  if (!/^(0|[1-9][0-9]*)$/.test(token)) throw new PatchError("invalid array index");
  const index = Number(token);
  if (!Number.isSafeInteger(index) || index >= length + Number(allowEnd)) {
    throw new PatchError("array index out of bounds");
  }
  return index;
}

function child(parent: JsonValue, token: string): JsonValue {
  if (Array.isArray(parent)) return parent[arrayIndex(token, parent.length, false)];
  if (parent !== null && typeof parent === "object") {
    if (!Object.prototype.hasOwnProperty.call(parent, token)) throw new PatchError("missing member");
    return parent[token];
  }
  throw new PatchError("cannot traverse a primitive");
}

function parentAt(root: JsonValue, tokens: readonly string[]): [JsonValue, string] {
  if (tokens.length === 0) throw new PatchError("root has no parent");
  let parent = root;
  for (const token of tokens.slice(0, -1)) parent = child(parent, token);
  return [parent, tokens[tokens.length - 1]];
}

export function readAt(root: JsonValue, tokens: readonly string[]): JsonValue {
  let value = root;
  for (const token of tokens) value = child(value, token);
  return value;
}

export function removeAt(root: JsonValue, tokens: readonly string[]): [JsonValue | undefined, JsonValue] {
  if (tokens.length === 0) return [undefined, root];
  const [parent, token] = parentAt(root, tokens);
  if (Array.isArray(parent)) {
    const index = arrayIndex(token, parent.length, false);
    return [root, parent.splice(index, 1)[0]];
  }
  if (parent !== null && typeof parent === "object") {
    if (!Object.prototype.hasOwnProperty.call(parent, token)) throw new PatchError("missing member");
    const value = parent[token];
    delete parent[token];
    return [root, value];
  }
  throw new PatchError("cannot remove from a primitive");
}

export function addAt(root: JsonValue | undefined, tokens: readonly string[], value: JsonValue): JsonValue {
  if (tokens.length === 0) return value;
  if (root === undefined) throw new PatchError("destination parent does not exist");
  const [parent, token] = parentAt(root, tokens);
  if (Array.isArray(parent)) {
    const index = token === "-" ? parent.length : arrayIndex(token, parent.length, true);
    parent.splice(index, 0, value);
  } else if (parent !== null && typeof parent === "object") {
    Object.defineProperty(parent, token, {value, writable: true, enumerable: true, configurable: true});
  } else {
    throw new PatchError("cannot add to a primitive");
  }
  return root;
}
