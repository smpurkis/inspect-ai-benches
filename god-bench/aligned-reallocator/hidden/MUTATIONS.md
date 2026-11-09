# Adequacy Matrix

The hidden suite was authored to reject these benchmark mutations:

| Mutation or bypass | Rejecting coverage |
| --- | --- |
| No-op/cached resize result | generated traces and kernel reachability |
| Always resize in place | forced moves, overlap traces, new alignment checks |
| Always move | in-place metamorph and deterministic offsets |
| Reverse free-range comparison | generated traces and coalesced reuse |
| Remove overflow/alignment checks | atomic overflow, OOM, and invalid alignments |
| Copy new length or omit copy | grow/shrink preservation checks with varied fill bytes |
| Free before replacement allocation | failure atomicity under OOM |
| Keep old handle valid after move/free | stale generation and forged-handle checks |
| Bypass candidate call site or add source | pristine scaffold reconstruction and sole artifact declaration |
