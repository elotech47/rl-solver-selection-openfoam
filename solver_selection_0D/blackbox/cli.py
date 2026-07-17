"""Command-line interface for the evaluation handoff."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

from .runner import run_from_config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="handoff.blackbox",
        description=(
            "Black-box 0-D evaluation of an RL chemistry-solver selection policy.\n"
            "Configure mechanism, model, observation flags, baselines, and plotting "
            "via a YAML file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples
--------
  # Run the shipped example (n-dodecane paper-style conditions)
  python -m handoff.blackbox --config handoff/configs/example_ndodecane.yaml

  # Override output directory and device without editing YAML
  python handoff/run.py --config handoff/configs/example_ndodecane.yaml \\
      --set output.dir=handoff_runs/demo --set device=cpu

  # Disable plotting; keep pkl + CSV only
  python handoff/run.py --config handoff/configs/example_ndodecane.yaml \\
      --set output.plot.enable=false

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
        "--repo-root",
        type=str,
        default=None,
        help=(
            "Repository root used to resolve relative mechanism/model paths. "
            "Default: the solver_selection project root."
        ),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve() if args.repo_root else None
    result = run_from_config(
        args.config,
        overrides=args.overrides or None,
        repo_root=repo_root,
    )
    print(f"\nOutputs written under: {result.output_dir}")
    return 0
