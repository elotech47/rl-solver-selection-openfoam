"""Black-box evaluation API (config-driven CVODE / QSS / RL / Sup-ML)."""

from .config import EvalConfig, load_config
from .runner import RunResult, run, run_from_config

__all__ = [
    "EvalConfig",
    "RunResult",
    "load_config",
    "run",
    "run_from_config",
]
