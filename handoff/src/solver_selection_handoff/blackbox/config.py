"""
Configuration schema, loading, validation, and CLI `--set` overrides.

The YAML file is the single source of truth for a black-box evaluation run.
See ``handoff/docs/CONFIG_REFERENCE.md`` for a field-by-field guide.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

import yaml

# Solver method names accepted in ``methods`` and plot compare lists.
KNOWN_METHODS = (
    "CVODE",
    "QSS",
    "RL-Adaptive",
    "Supervised-ML",
)

DEFAULT_NETWORK = {
    "hidden_dims": [256, 128, 64],
    "activation": "relu",
}

DEFAULT_SOLVER = {
    "ref_rtol": 1.0e-10,
    "ref_atol": 1.0e-20,
    "cvode_rtol": 1.0e-8,
    "cvode_atol": 1.0e-12,
    "qss_dtmin": 1.0e-12,
    "qss_dtmax": 1.0e-6,
    "qss_abstol": 1.0e-11,
    "qss_itermax": 2,
    "epsmin": 0.02,
    "epsmax": 100.0,
    "mxsteps": 100000,
    "num_steps": 20,
}

DEFAULT_KEY_SPECIES = [
    "OH", "H2O", "O2", "H2", "H2O2", "O", "H", "N2",
]

DEFAULT_PLOT_SPECIES = ["OH", "CO2", "H2O"]


def _deep_update(base: dict, overrides: dict) -> dict:
    """Recursively merge ``overrides`` into ``base`` (mutates and returns base)."""
    for key, value in overrides.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _parse_set_value(raw: str) -> Any:
    """Parse a CLI ``--set key=value`` right-hand side to a Python object."""
    text = raw.strip()
    lower = text.lower()
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False
    if lower in ("null", "none", "~"):
        return None
    try:
        if "." in text or "e" in lower:
            return float(text)
        return int(text)
    except ValueError:
        pass
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_set_value(part.strip()) for part in inner.split(",")]
    return text


def apply_set_overrides(cfg: dict, sets: Sequence[str]) -> dict:
    """
    Apply ``section.key=value`` (dot-path) overrides onto a config dict.

    Examples
    --------
    >>> apply_set_overrides(cfg, ["device=cuda", "policy.use_gradient_only=true"])
    """
    out = copy.deepcopy(cfg)
    for item in sets:
        if "=" not in item:
            raise ValueError(
                f"Invalid --set '{item}'. Expected KEY=VALUE "
                f"(e.g. policy.use_gradient_only=false)."
            )
        path, raw = item.split("=", 1)
        keys = [k for k in path.strip().split(".") if k]
        if not keys:
            raise ValueError(f"Empty key in --set '{item}'.")
        cursor: dict = out
        for key in keys[:-1]:
            if key not in cursor or not isinstance(cursor[key], dict):
                cursor[key] = {}
            cursor = cursor[key]
        cursor[keys[-1]] = _parse_set_value(raw)
    return out


@dataclass
class ConditionSpec:
    """One 0-D homogeneous reactor initial condition."""

    temp: float
    pressure_atm: float
    Z: float
    dt: float
    t_end: float
    label: Optional[str] = None
    phi: Optional[float] = None  # alternative to Z; mutually exclusive in practice

    def display_label(self) -> str:
        if self.label:
            return self.label
        return f"{self.temp:.0f}K, {self.pressure_atm:g}atm, Z={self.Z:g}"

    def filename_tag(self) -> str:
        return (
            f"{self.temp:.0f}K_{self.pressure_atm:.1f}atm_{self.Z}"
        )


@dataclass
class PlotConfig:
    enable: bool = True
    style: str = "comparison"  # comparison | temperature_only
    species: List[str] = field(default_factory=lambda: list(DEFAULT_PLOT_SPECIES))
    formats: List[str] = field(default_factory=lambda: ["png", "pdf"])
    dpi: int = 300
    compare_methods: Optional[List[str]] = None  # None = plot all methods that ran


@dataclass
class EvalConfig:
    """
    Fully resolved black-box evaluation configuration.

    Construct via :func:`load_config` rather than by hand whenever possible.
    """

    # Paths / mechanism
    mechanism: str  # path or named key (ndodecane, methane, ...)
    mechanism_path: Path
    fuel: str
    oxidizer: str
    key_species: List[str]

    # Policy
    model_path: Path
    network: Dict[str, Any]
    use_prev_state: bool
    use_gradient_only: bool
    confidence_threshold: float
    num_steps: int

    # What to run
    methods: List[str]
    conditions: List[ConditionSpec]

    # Supervised baseline (optional)
    supervised_model_dir: Optional[Path]
    supervised_error_threshold: float

    # Solver tolerances
    solver: Dict[str, Any]

    # Runtime
    device: str
    n_repeats: int
    record_trajectory: bool

    # Output / plotting
    output_dir: Path
    save_pkl: bool
    save_summary_csv: bool
    plot: PlotConfig

    # Raw YAML (for snapshotting)
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def solver_config_for_pipeline(self) -> Dict[str, Any]:
        """TOL / observation flags passed into ``CompletePipeline``."""
        cfg = dict(self.solver)
        cfg["use_prev_state"] = self.use_prev_state
        cfg["use_gradient_only"] = self.use_gradient_only
        cfg["num_steps"] = self.num_steps
        cfg["use_prev_state"] = bool(self.use_prev_state)
        return cfg


def _require(cfg: dict, *keys: str, context: str = "config") -> Any:
    cursor: Any = cfg
    trail: List[str] = []
    for key in keys:
        trail.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            raise KeyError(
                f"Missing required field '{'.'.join(trail)}' in {context}."
            )
        cursor = cursor[key]
    return cursor


def _as_path(value: Optional[Union[str, Path]], base: Path) -> Optional[Path]:
    if value is None or value == "":
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base / path).resolve()
    else:
        path = path.resolve()
    return path


def _resolve_mechanism(
    raw: dict,
    base_dir: Path,
) -> tuple[str, Path, str, str, List[str]]:
    """
    Resolve mechanism path + fuel/oxidizer/key_species.

    Accepts either:
      - ``mechanism: ndodecane`` (named key from packaged MECHANISM_CONFIGS), or
      - ``mechanism: path/to/file.yaml`` plus explicit ``fuel`` / ``oxidizer``.
    """
    from solver_selection_handoff.utils import (
        MECHANISM_CONFIGS,
        resolve_mechanism_path,
    )

    mech_field = raw.get("mechanism")
    if mech_field is None:
        raise KeyError("Missing required field 'mechanism'.")

    mech_str = str(mech_field).strip()
    named = MECHANISM_CONFIGS.get(mech_str)

    if named is not None:
        mechanism_path = resolve_mechanism_path(mech_str)
        # Built-in Cantera names (e.g. h2o2.yaml) may not exist as Path.is_file().
        if named.get("package_resource", False) and not mechanism_path.is_file():
            raise FileNotFoundError(f"Packaged mechanism not found: {mechanism_path}")
        fuel = raw.get("fuel", named["fuel"])
        oxidizer = raw.get("oxidizer", named["oxidizer"])
        key_species = list(raw.get("key_species", named["key_species"]))
        return mech_str, mechanism_path, fuel, oxidizer, key_species

    # Treat as filesystem path relative to config dir / CWD / absolute.
    mechanism_path = _as_path(mech_str, base_dir)
    assert mechanism_path is not None
    if not mechanism_path.is_file():
        known = ", ".join(sorted(MECHANISM_CONFIGS))
        raise FileNotFoundError(
            f"Mechanism file not found: {mechanism_path}\n"
            f"Use a path to a Cantera YAML, or one of: {known}."
        )
    fuel = raw.get("fuel")
    oxidizer = raw.get("oxidizer")
    if not fuel or not oxidizer:
        raise KeyError(
            "When 'mechanism' is a file path, you must also set "
            "'fuel' and 'oxidizer' (Cantera composition strings)."
        )
    key_species = list(raw.get("key_species", DEFAULT_KEY_SPECIES))
    return mech_str, mechanism_path, str(fuel), str(oxidizer), key_species


def _parse_conditions(raw_list: Sequence[dict]) -> List[ConditionSpec]:
    if not raw_list:
        raise ValueError(
            "Config must define at least one entry under 'conditions:'."
        )
    out: List[ConditionSpec] = []
    for i, item in enumerate(raw_list):
        missing = [
            k for k in ("temp", "pressure_atm", "dt", "t_end") if k not in item
        ]
        if missing:
            raise KeyError(
                f"conditions[{i}] missing fields: {missing}."
            )
        if "Z" not in item and "phi" not in item:
            raise KeyError(
                f"conditions[{i}] must set either 'Z' (mixture fraction) "
                f"or 'phi' (equivalence ratio)."
            )
        out.append(
            ConditionSpec(
                temp=float(item["temp"]),
                pressure_atm=float(item["pressure_atm"]),
                Z=float(item.get("Z", 0.0)),
                dt=float(item["dt"]),
                t_end=float(item["t_end"]),
                label=item.get("label"),
                phi=float(item["phi"]) if item.get("phi") is not None else None,
            )
        )
    return out


def _parse_methods(raw: dict, has_supervised: bool) -> List[str]:
    methods = list(raw.get("methods", ["CVODE", "QSS", "RL-Adaptive"]))
    unknown = [m for m in methods if m not in KNOWN_METHODS]
    if unknown:
        raise ValueError(
            f"Unknown method(s) {unknown}. Allowed: {list(KNOWN_METHODS)}."
        )
    if "RL-Adaptive" not in methods:
        raise ValueError(
            "methods must include 'RL-Adaptive' (the primary policy under test)."
        )
    if "Supervised-ML" in methods and not has_supervised:
        raise ValueError(
            "methods includes 'Supervised-ML' but "
            "supervised.model_dir is not set."
        )
    return methods


def load_config(
    path: Union[str, Path],
    *,
    overrides: Optional[Sequence[str]] = None,
    workdir: Optional[Path] = None,
    repo_root: Optional[Path] = None,  # deprecated alias for workdir
) -> EvalConfig:
    """
    Load and validate a YAML evaluation config.

    Parameters
    ----------
    path:
        Path to the YAML file.
    overrides:
        Optional list of ``key.subkey=value`` strings (same as CLI ``--set``).
    workdir:
        Directory used to resolve relative *model* and *output* paths.
        Defaults to the current working directory. Named mechanisms are always
        resolved from package data (not from this directory).
    repo_root:
        Deprecated alias for ``workdir`` (kept for older CLIs).
    """
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config not found: {config_path}")

    if workdir is None:
        workdir = repo_root if repo_root is not None else Path.cwd()
    workdir = Path(workdir).expanduser().resolve()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"Config root must be a mapping, got {type(raw)}.")

    if overrides:
        raw = apply_set_overrides(raw, overrides)

    config_dir = config_path.parent

    # ---- mechanism (named keys → packaged data/) ----
    mech_key, mechanism_path, fuel, oxidizer, key_species = _resolve_mechanism(
        raw, config_dir
    )
    from solver_selection_handoff.utils import MECHANISM_CONFIGS as _MC

    named_cfg = _MC.get(mech_key)
    if named_cfg is None or named_cfg.get("package_resource", False):
        if not mechanism_path.is_file():
            raise FileNotFoundError(f"Mechanism file not found: {mechanism_path}")

    # ---- policy ----
    policy = raw.get("policy", {}) or {}
    model_raw = policy.get("model_path") or raw.get("model_path")
    if not model_raw:
        raise KeyError("Missing required field 'policy.model_path'.")
    model_path = _as_path(model_raw, config_dir)
    assert model_path is not None
    if not model_path.is_file():
        alt = _as_path(model_raw, workdir)
        if alt is not None and alt.is_file():
            model_path = alt
        else:
            raise FileNotFoundError(
                f"RL checkpoint not found: {model_path}\n"
                f"(also checked under workdir={workdir})"
            )

    network = dict(DEFAULT_NETWORK)
    network.update(policy.get("network") or raw.get("network") or {})

    use_prev_state = bool(policy.get("use_prev_state", True))
    use_gradient_only = bool(policy.get("use_gradient_only", False))
    confidence_threshold = float(policy.get("confidence_threshold", 0.6))
    num_steps = int(
        policy.get(
            "num_steps",
            (raw.get("solver") or {}).get("num_steps", DEFAULT_SOLVER["num_steps"]),
        )
    )

    if use_prev_state and use_gradient_only:
        # Allowed but redundant — observation will follow use_gradient_only.
        pass

    # ---- supervised ----
    supervised = raw.get("supervised") or {}
    supervised_dir = _as_path(supervised.get("model_dir"), workdir)
    if supervised_dir is not None and not supervised_dir.is_dir():
        # Try relative to config file.
        alt = _as_path(supervised.get("model_dir"), config_dir)
        if alt is not None and alt.is_dir():
            supervised_dir = alt
        else:
            raise NotADirectoryError(
                f"supervised.model_dir is not a directory: {supervised_dir}"
            )
    supervised_threshold = float(supervised.get("error_threshold", 1.0e-4))

    # ---- methods / conditions ----
    methods = _parse_methods(raw, has_supervised=supervised_dir is not None)
    conditions = _parse_conditions(raw.get("conditions") or [])

    # ---- solver tolerances ----
    solver = dict(DEFAULT_SOLVER)
    solver.update(raw.get("solver") or {})
    # Keep num_steps consistent with policy.
    solver["num_steps"] = num_steps

    # ---- output ----
    output = raw.get("output") or {}
    out_dir = _as_path(output.get("dir", "handoff_runs/default"), workdir)
    assert out_dir is not None

    plot_raw = output.get("plot") or {}
    compare = plot_raw.get("compare_methods")
    if compare is not None:
        compare = list(compare)
        unknown = [m for m in compare if m not in KNOWN_METHODS]
        if unknown:
            raise ValueError(f"plot.compare_methods unknown: {unknown}")

    plot = PlotConfig(
        enable=bool(plot_raw.get("enable", True)),
        style=str(plot_raw.get("style", "comparison")),
        species=list(plot_raw.get("species") or DEFAULT_PLOT_SPECIES),
        formats=list(plot_raw.get("formats") or ["png", "pdf"]),
        dpi=int(plot_raw.get("dpi", 300)),
        compare_methods=compare,
    )

    device = str(raw.get("device", "cpu"))
    n_repeats = max(1, int(raw.get("n_repeats", 1)))
    record_trajectory = bool(raw.get("record_trajectory", True))

    return EvalConfig(
        mechanism=mech_key,
        mechanism_path=mechanism_path,
        fuel=fuel,
        oxidizer=oxidizer,
        key_species=key_species,
        model_path=model_path,
        network=network,
        use_prev_state=use_prev_state,
        use_gradient_only=use_gradient_only,
        confidence_threshold=confidence_threshold,
        num_steps=num_steps,
        methods=methods,
        conditions=conditions,
        supervised_model_dir=supervised_dir,
        supervised_error_threshold=supervised_threshold,
        solver=solver,
        device=device,
        n_repeats=n_repeats,
        record_trajectory=record_trajectory,
        output_dir=out_dir,
        save_pkl=bool(output.get("save_pkl", True)),
        save_summary_csv=bool(output.get("save_summary_csv", True)),
        plot=plot,
        raw=raw,
    )
