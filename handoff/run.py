#!/usr/bin/env python
"""
Convenience launcher (works from a source checkout *or* after install).

Preferred (after install)::

    pip install -e handoff/
    solver-selection-eval --config handoff/configs/example_minimal.yaml

Or::

    python -m solver_selection_handoff --config ...
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow ``python handoff/run.py`` before/without install by putting src/ on path.
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from solver_selection_handoff.blackbox.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
