# Layout Contract

Only `src/Layout.hs` is editable. It must export exactly `LayoutError(..)` and `insertLayout` with the supplied types.

`insertLayout` receives non-layout tokens in source order. Positions are one-based. Tokens on one physical line have strictly increasing columns. The tokenizer recognizes identifiers, `let`, `where`, `in`, `=`, parentheses, braces, and semicolons; strips `--` comments and blank lines; and rejects tabs and unknown characters.

Rules:

1. A nonempty file is an implicit root block at the first token's column and is wrapped in `TVOpen` and `TVClose`. Empty input produces no tokens.
2. `let` and `where` introduce a block. If the next token is `{`, that brace starts an explicit block and no virtual open is inserted. Otherwise insert `TVOpen` immediately before the next token and use that token's column as the block indentation.
3. On the first token of a later nonblank line, equal indentation in the active implicit block inserts `TVSemi`. Lower indentation closes implicit blocks until a level matches. If no active implicit level matches, report `BadDedent line column`.
4. An explicit block suspends indentation handling for the implicit blocks outside it. Implicit blocks introduced inside it still use rules 2 and 3. `}` first closes any implicit blocks nested in its matching explicit block, then closes that explicit block.
5. `in` closes the nearest still-open implicit block introduced by `let`, including a same-line block. It does not insert a semicolon before `in` merely because columns match.
6. EOF closes all implicit blocks. An unmatched `}` is `UnexpectedClose`; an open explicit block at EOF is `UnclosedExplicit`; a layout introducer at EOF is `MissingBlock`.
7. Existing explicit semicolons remain `TSemi`; never insert `TVSemi` adjacent to `;`, `{`, or immediately before `}` or `in`.

The trusted parser accepts declarations `name = expression`, nested `let BLOCK in expression`, and postfix `where BLOCK`; expressions may use identifiers and parentheses. The CLI's `layout` mode prints one token per line and its `parse` mode validates the supplied parser. Hidden tests call both modes and compile direct kernel probes.
