#!/usr/bin/env python3
"""Export policy_manifest.json → OpenFOAM dictionary for C++ loadPolicyManifest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JSON = ROOT / "policy" / "policy_manifest.json"
DEFAULT_OUT = ROOT / "policy" / "policy_manifest"


def fmt_list(name: str, vals: list, indent: str = "    ") -> str:
    lines = [f"{indent}{name}"]
    lines.append(f"{indent}(")
    for v in vals:
        if isinstance(v, float):
            lines.append(f"{indent}    {v!r}".replace("'", ""))
        else:
            lines.append(f"{indent}    {v}")
    lines.append(f"{indent});")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    man = json.loads(args.json.read_text())

    # Foam dictionary (ASCII). Paths relative to case or absolute under /work.
    body = []
    body.append("FoamFile")
    body.append("{")
    body.append("    version     2.0;")
    body.append("    format      ascii;")
    body.append("    class       dictionary;")
    body.append("    object      policy_manifest;")
    body.append("}")
    body.append("")
    body.append(f"obs_dim              {man['obs_dim']};")
    body.append(f"confidence_threshold {man['confidence_threshold']};")
    body.append(f"num_steps            {man['num_steps']};")
    body.append(f"obs_clip             {man.get('obs_clip', 10.0)};")
    body.append(f'torchScript          "{man.get("torchscript", "policy.ts")}";')
    body.append("")
    body.append("key_species")
    body.append("(")
    for s in man["key_species"]:
        body.append(f"    {s.lower()}")  # foam thermo uses lowercase
    body.append(");")
    body.append("")
    body.append(fmt_list("obs_rms_mean", man["obs_rms_mean"]))
    body.append("")
    body.append(fmt_list("obs_rms_var", man["obs_rms_var"]))
    body.append("")

    args.out.write_text("\n".join(body) + "\n")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
