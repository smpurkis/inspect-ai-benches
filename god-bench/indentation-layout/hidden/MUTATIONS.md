# Mutation adequacy map

The generated and adversarial tests are intended to kill these authoring mutations:

- omit virtual opens/closes or semicolons: generated oracle and nested parser cases;
- reverse either indentation comparison: translated layouts and malformed dedents;
- treat comments or blank lines as layout points: decoration metamorphism;
- apply indentation through explicit braces: explicit suspension cases;
- close the wrong `let` at `in`: nested and same-line `let` parser cases;
- accept unmatched braces or an introducer at EOF: malformed boundary cases;
- bypass the submitted kernel: single-definition and compiled-artifact reachability check.
