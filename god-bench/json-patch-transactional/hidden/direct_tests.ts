declare const process: any;

import { applyOperation } from "./applyOperation";

function check(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

const source: any = {nested: {items: [1, {x: 2}]}};
const copied: any = applyOperation(source, {op: "copy", from: "/nested", path: "/clone"});
check(copied === source, "non-root success must retain root identity");
check(copied.clone !== copied.nested, "copy aliases source object");
check(copied.clone.items !== copied.nested.items, "copy aliases nested array");
check(copied.clone.items[1] !== copied.nested.items[1], "copy aliases nested object");
copied.clone.items[1].x = 99;
check(copied.nested.items[1].x === 2, "copy mutation reached source");

const rollback: any = {keep: {v: 1}, moving: [2, 3]};
const before = JSON.stringify(rollback);
let threw = false;
try {
  applyOperation(rollback, {op: "move", from: "/moving", path: "/keep/missing/child"});
} catch (_) {
  threw = true;
}
check(threw && JSON.stringify(rollback) === before, "move failure was not atomic");

const same: any = {a: [1, 2]};
check(applyOperation(same, {op: "move", from: "/a", path: "/a"}) === same, "same path is not a no-op");
process.stdout.write("direct checks passed\n");
