# Transactional JSON Patch

Edit only `src/applyOperation.ts`; the intended patch is 60-110 lines. Implement the existing function:

```ts
applyOperation(document: JsonValue, operation: Operation): JsonValue
```

Support exactly RFC 6902 `move` and `copy`. JSON pointers use RFC 6901 escaping (`~0`, `~1`), the empty string denotes the root, array indexes are canonical decimal tokens, and `-` is accepted only as the final add destination. The trusted `pointer.ts` exports parsing and primitive read/remove/add operations; it deliberately does not provide transaction or operation semantics.

`copy` reads `from`, recursively clones its JSON value, and adds the clone at `path`. No object or array in the new value may alias the source. `move` is equivalent to removing `from` and then adding that exact value at `path`, so indexes are interpreted after removal. Moving to the same pointer is a successful no-op. Moving a value into its own proper descendant is invalid, comparing decoded pointer tokens rather than raw strings.

On success, mutate the supplied root object or array in place and return it. A root-path destination necessarily returns a replacement root. On any `PatchError`, including a destination error discovered after a move source was removed, restore the supplied document to the exact JSON value it held before the call and rethrow. Inputs are JSON values: no cycles, accessors, symbols, `undefined`, or non-finite numbers.

Do not import anything except `./pointer` and `./types`. Do not access the filesystem, environment, network, subprocesses, dynamic code evaluation, or generated JavaScript. Build and test:

```text
make -C /app/files clean all
python3 -m pytest -q /app/files/tests.py
```

No other source file, build configuration, dependency, or generated artifact may be submitted.
