# SamScript bootstrap runtime

Edit only `/app/files/runtime.py`. The supplied scanner, parser, expression evaluator, builtins, imports, and CLI are complete. Implement lexical scope lookup/assignment and statement execution so `return`, `break`, and `continue` propagate to the correct function or loop.

Blocks create scopes. Shadowing never changes an outer binding, while assignment updates the nearest existing binding. Function calls have isolated frames; block scopes must be unwound on every control path. Loops consume only their own `break`/`continue`; functions consume only `return`. Invalid escaped control raises `RuntimeFault`.

Run `python3 -m pytest -q /app/files/tests.py`. Work offline and do not modify scaffold files.
