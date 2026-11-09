# Adequacy Matrix

The hidden suite was authored to reject these benchmark mutations:

| Mutation or bypass | Rejecting coverage |
| --- | --- |
| Empty/no-op query or cached constant | generated oracle cases and kernel reachability |
| Reverse either interval boundary comparison | exact valid/system boundary case |
| Omit valid or system end bound | generated finite intervals |
| Omit tenant, subject, or key predicate | metamorphic decoy insertion |
| Reverse precedence or omit revision tie | generated overlaps and exact ties |
| Ignore tombstones | retroactive tombstone boundary |
| Depend on insertion order | generated shuffle and reversed metamorph |
| Bypass candidate with writes or external access | read-only structural policy plus pristine scaffold |
