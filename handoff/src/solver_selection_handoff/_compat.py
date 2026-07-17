"""
Back-compat import aliases for torch checkpoints pickled against the
original flat research-repo module names (``ppo_agent``, …).

Import this module *before* ``torch.load`` of any training checkpoint.
Only aliases modules that do not create import cycles with ``inference``.
"""

from __future__ import annotations

import sys

import solver_selection_handoff.ppo_agent as _ppo_agent
import solver_selection_handoff.utils as _utils
import solver_selection_handoff.train_supervised_nets as _train_supervised_nets

# Flat names that may appear inside checkpoint pickles.
_ALIASES = {
    "ppo_agent": _ppo_agent,
    "utils": _utils,
    "train_supervised_nets": _train_supervised_nets,
}


def install_flat_module_aliases() -> None:
    """Register flat module names on ``sys.modules`` if missing."""
    for name, mod in _ALIASES.items():
        sys.modules.setdefault(name, mod)


install_flat_module_aliases()
