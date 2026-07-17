"""Command-line interface for the evaluation handoff."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .runner import run_from_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="solver-selection-eval",
        description=(
            "Self-contained black-box 0-D evaluation of an RL chemistry-solver "
            "selection policy (CVODE vs QSS, optional Supervised-ML)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # After: pip install -e handoff/
  solver-selection-eval --config handoff/configs/example_minimal.yaml \\
      --set policy.model_path=/path/to/policy.pt

  # Module form (no console script):
  python -m solver_selection_handoff --config handoff/configs/example_minimal.yaml

Documentation
-------------
  handoff/README.md
  handoff/docs/CONFIG_REFERENCE.md
  handoff/docs/ARCHITECTURE.md
""".strip(),
    )
    p.add_argument(
        "--config",
        "-c",
        type=str,
        required=True,
        help="Path to the YAML evaluation configuration.",
    )
    p.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Override a config field (repeatable). Dot-paths allowed, e.g. "
            "policy.use_gradient_only=true or output.dir=my_run."
        ),
    )
    p.add_argument(
        "--workdir",
        type=str,
        default=None,
        help=(
            "Directory for resolving relative model/output paths "
            "(default: current working directory). Named mechanisms always "
            "come from packaged data."
        ),
    )
    # Back-compat alias
    p.add_argument(
        "--repo-root",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    workdir = args.workdir or args.repo_root
    workdir_path = Path(workdir).resolve() if workdir else None
    result = run_from_config(
        args.config,
        overrides=args.overrides or None,
        workdir=workdir_path,
    )
    print(f"\nOutputs written under: {result.output_dir}")
    return 0
