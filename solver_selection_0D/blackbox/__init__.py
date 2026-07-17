"""
Professional black-box evaluation handoff for adaptive chemistry solver selection.

Public API
----------
    from handoff.blackbox import run_from_config, load_config, RunResult

    result = run_from_config("handoff/configs/example_ndodecane.yaml")

CLI
---
    python -m handoff.blackbox --config handoff/configs/example_ndodecane.yaml
    python handoff/run.py --config handoff/configs/example_ndodecane.yaml
"""

from .config import EvalConfig, load_config
from .runner import RunResult, run, run_from_config

__all__ = [
    "EvalConfig",
    "RunResult",
    "load_config",
    "run",
    "run_from_config",
]

__version__ = "1.0.0"
