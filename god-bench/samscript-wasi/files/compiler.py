#!/usr/bin/env python3
"""Implement the SamScript-to-WASI compiler in this file."""

import sys


def main() -> int:
    print("samscript: compiler not yet implemented", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
