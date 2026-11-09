export type JsonPrimitive = null | boolean | number | string;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export interface MoveOperation {
  op: "move";
  from: string;
  path: string;
}

export interface CopyOperation {
  op: "copy";
  from: string;
  path: string;
}

export type Operation = MoveOperation | CopyOperation;

export class PatchError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PatchError";
  }
}
