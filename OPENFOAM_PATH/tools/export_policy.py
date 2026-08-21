#!/usr/bin/env python3
"""Export best_offline_eval2.pt → TorchScript + policy_manifest.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CKPT = ROOT / "policy" / "best_offline_eval2.pt"
OUT_DIR = ROOT / "policy"


class ActorHead(nn.Module):
    """Traceable actor: feature_extractor + actor logits (matches handoff ActorCriticNetwork)."""

    def __init__(self, feature_extractor: nn.Module, actor: nn.Linear):
        super().__init__()
        self.feature_extractor = feature_extractor
        self.actor = actor

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.actor(self.feature_extractor(x))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", type=Path, default=DEFAULT_CKPT)
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if not args.checkpoint.is_file():
        print(f"Missing {args.checkpoint}", file=sys.stderr)
        return 1

    from solver_selection_handoff.ppo_agent import PPOAgent, PPOConfig

    ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    network_state = ckpt["network_state_dict"]
    obs_dim = network_state["feature_extractor.0.weight"].shape[1]
    action_dim = network_state["actor.weight"].shape[0]
    network_config = {"hidden_dims": [256, 128, 64], "activation": "relu"}
    agent = PPOAgent(
        obs_dim=obs_dim,
        action_dim=action_dim,
        config=ckpt.get("config", PPOConfig()),
        network_config=network_config,
    )
    agent.network.load_state_dict(network_state)
    agent.network.eval()

    export_net = ActorHead(agent.network.feature_extractor, agent.network.actor)
    export_net.eval()
    example = torch.zeros(1, obs_dim)
    ts_path = args.out_dir / "policy.ts"
    # check_trace=False: torch>=2.10 can SystemError in graph diagnostics on some hosts
    torch.jit.trace(export_net, example, check_trace=False).save(str(ts_path))

    obs_mean = np.asarray(ckpt["obs_rms"]["mean"]).astype(float).tolist()
    obs_var = np.asarray(ckpt["obs_rms"]["var"]).astype(float).tolist()

    manifest = {
        "obs_dim": int(obs_dim),
        "feature_order": [
            "T_norm",
            "log10_Y_OH",
            "log10_Y_H2O",
            "log10_Y_O2",
            "log10_Y_H2",
            "log10_Y_H2O2",
            "log10_Y_O",
            "log10_Y_H",
            "log10_Y_N2",
            "P_norm",
            "dlog10_T",
            "dlog10_Y_OH",
            "dlog10_Y_H2O",
            "dlog10_Y_O2",
            "dlog10_Y_H2",
            "dlog10_Y_H2O2",
            "dlog10_Y_O",
            "dlog10_Y_H",
            "dlog10_Y_N2",
        ],
        "hand_norms": {
            "T_norm": "(T-300)/2000",
            "Y": "log10(max(|Y|,1e-20))",
            "P_norm": "log10(P/one_atm)",
            "temporal": "Δlog10, NOT divided by dt",
        },
        "key_species": ["OH", "H2O", "O2", "H2", "H2O2", "O", "H", "N2"],
        "obs_rms_mean": obs_mean,
        "obs_rms_var": obs_var,
        "obs_clip": 10.0,
        "hidden_dims": [256, 128, 64],
        "activation": "relu",
        "confidence_threshold": 0.6,
        "num_steps": 20,
        "action_map": {"0": "CVODE", "1": "QSS"},
        "decision_rule": "argmax logits; if softmax(confidence)<0.6 force CVODE",
        "torchscript": ts_path.name,
        "source_checkpoint": args.checkpoint.name,
    }
    man_path = args.out_dir / "policy_manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2))
    print(f"Wrote {ts_path}")
    print(f"Wrote {man_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
