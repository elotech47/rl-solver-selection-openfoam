#!/usr/bin/env python
"""
Top-level launcher for the evaluation handoff.

Usage
-----
    python handoff/run.py --config handoff/configs/example_ndodecane.yaml
    python handoff/run.py --config handoff/configs/example_ndodecane.yaml \\
        --set output.dir=my_run --set device=cpu
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as ``python handoff/run.py`` without installing the package.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from handoff.blackbox.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
