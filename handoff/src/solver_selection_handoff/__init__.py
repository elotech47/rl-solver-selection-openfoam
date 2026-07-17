"""
solver_selection_handoff
========================

Self-contained, installable evaluation package for RL-based chemistry
solver selection (CVODE vs QSS) on 0-D homogeneous reactors.

Public entry points
-------------------
CLI::

    solver-selection-eval --config path/to/config.yaml

Python::

    from solver_selection_handoff import run_from_config
    run_from_config("config.yaml")
"""

from solver_selection_handoff import _compat  # noqa: F401  — checkpoint aliases

from solver_selection_handoff.blackbox import (
    EvalConfig,
    RunResult,
    load_config,
    run,
    run_from_config,
)

__all__ = [
    "EvalConfig",
    "RunResult",
    "load_config",
    "run",
    "run_from_config",
    "__version__",
]

__version__ = "1.0.0"
