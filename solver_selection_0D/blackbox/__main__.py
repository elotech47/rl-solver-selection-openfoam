#!/usr/bin/env python
"""CLI entry: ``python -m handoff.blackbox --config PATH``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
