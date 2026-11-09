# Indentation Layout Inserter

Edit only `src/Layout.hs`. Repair `insertLayout` without changing its exported API. The trusted tokenizer supplies positioned tokens, and the trusted parser consumes the resulting explicit and virtual delimiters.

The language has top-level declarations and layout blocks introduced by `let` and `where`. A block starts at the column of its first token unless the introducer is followed by `{`. Equal indentation inserts `TVSemi`; a dedent closes blocks with `TVClose`; an indentation that matches no enclosing implicit level is `BadDedent`. `in` closes its nearest implicit `let` block. Explicit braces disable indentation relative to their contents but may contain nested implicit blocks. Comments and blank lines are removed by the tokenizer and do not affect layout. EOF closes every implicit block and rejects unclosed explicit braces. See `/app/files/TASK.md` for the complete contract and examples.

Build and run the public suite with `/app/files/run_tests.sh public`. No dependencies or network access are permitted.
