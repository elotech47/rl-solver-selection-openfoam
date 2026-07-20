#!/usr/bin/env python3
"""E17 three-mode smoke wall-time ratio + gate summary."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True)
    args = ap.parse_args()
    rows = []
    for mode in ("cvodeOnly", "qssOnly", "rlAdaptive"):
        d = args.base / mode
        s = d / "summary.json"
        if not s.is_file():
            s = d / "extract" / "summary.json"
        if s.is_file():
            rows.append(json.loads(s.read_text()))
        else:
            rows.append({"mode": mode, "missing": True})

    cv_wall = next((r.get("wall_s") for r in rows if r.get("mode") == "cvodeOnly"), None)
    report = {"modes": rows, "wall_ratio_vs_cvode": {}}
    if cv_wall and cv_wall > 0:
        for r in rows:
            w = r.get("wall_s")
            if w:
                report["wall_ratio_vs_cvode"][r.get("mode", "?")] = w / cv_wall

    out = args.base / "smoke_summary.json"
    out.write_text(json.dumps(report, indent=2))
    print("=== E17 three-mode wall-time ratio (first 2D cost datum) ===")
    for mode, ratio in report["wall_ratio_vs_cvode"].items():
        w = next((r["wall_s"] for r in rows if r.get("mode") == mode), None)
        print(f"  {mode}: wall={w}s  ratio/cvode={ratio:.3f}x")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
