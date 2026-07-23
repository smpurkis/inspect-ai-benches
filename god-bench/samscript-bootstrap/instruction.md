# Self-hosted SamScript interpreter

Edit only `/app/files/samscript_bootstrap.sam`. Implement a SamScript program that reads and executes another SamScript program when invoked as:

```text
/app/target/release/samscript run /app/files/samscript_bootstrap.sam -- run program.sam
```

Its stdout and error behavior must match the reference interpreter for valid and invalid inputs. Work offline; do not invoke another interpreter from the solution or use canned output. The language contract and bootstrap builtins are in `language_spec.md`.

Run `python3 -m pytest -q /app/files/tests.py`.
