import numpy as np
import cantera as ct
import time
from typing import Dict, Any, List, Optional, Tuple, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
import json

import torch
import matplotlib.pyplot as plt
from tqdm import tqdm
import seaborn as sns

from .solver_strategy import SolverStrategy, CVODEStrategy, QSSStrategy, ReferenceStrategy, integrate_loop
from .inference import RLSolverSelector
from .train_supervised_nets import MLP, EPS_Y, EPS_ERR


@dataclass
class EvaluationConfig:
    """Configuration for solver evaluation."""
    dt: float
    t_end: float
    pressure: float
    record_trajectory: bool = True
    use_old_observation: bool = False
    use_prev_state: bool = True
    use_gradient_only: bool = False


class ObservationBuilder:
    """Constructs observations for the RL agent from simulation state."""
    
    def __init__(self, species_indices: List[int], use_old_observation: bool = False, use_gradient_only: bool = False,
                 use_prev_state: bool = True):
        self.species_indices = species_indices
        self.use_old_observation = use_old_observation
        self.use_prev_state = use_prev_state
        self.use_gradient_only = use_gradient_only
        self.prev_states = None
    
    def reset(self, initial_state: np.ndarray):
        """Reset the observation builder with initial state."""
        temp = initial_state[0]
        Y = initial_state[1:]
        Y_key = np.array([Y[i] for i in self.species_indices])
        self.prev_states = [temp, Y_key]
    
    def build(self, states: np.ndarray, pressure: float) -> np.ndarray:
        """Build observation from current state."""
        temp = states[0]
        Y = states[1:]
        Y_key = np.array([Y[i] for i in self.species_indices])
        
        if self.use_old_observation:
            return self._build_legacy_observation(temp, Y_key, pressure)
        
        return self._build_normalized_observation(temp, Y_key, pressure)
    
    def _build_legacy_observation(self, temp: float, Y_key: np.ndarray, 
                                   pressure: float) -> np.ndarray:
        """Legacy observation format (for backward compatibility)."""
        return np.concatenate([
            [np.log10(temp)],
            np.log10(np.maximum(np.abs(Y_key), 1e-20)),
            [np.log10(pressure)]
        ]).astype(np.float32)
    
    def _build_normalized_observation(self, temp: float, Y_key: np.ndarray, 
                                       pressure: float) -> np.ndarray:
        """Normalized observation with optional temporal features."""
        # Normalize features
        T_norm = (temp - 300.0) / 2000.0
        P_norm = np.log10(pressure / ct.one_atm)
        Y_key_trans = np.log10(np.maximum(np.abs(Y_key), 1e-20))
        
        obs_components = np.concatenate([[T_norm], Y_key_trans, [P_norm]]).astype(np.float32)

        if self.use_gradient_only:
            prev_temp, prev_Y = self.prev_states
            prev_Y_key = np.asarray(prev_Y)
            prev_Y_key_trans = np.log10(np.maximum(np.abs(prev_Y_key), 1e-20))
            
            dTdt = (np.log10(temp) - np.log10(prev_temp))
            dYdt = (Y_key_trans - prev_Y_key_trans)
            obs_components = np.concatenate([[dTdt], dYdt, [P_norm]]).astype(np.float32)

            self.prev_states = [temp, Y_key]
            return obs_components
        
        # Add temporal derivatives if enabled
        if self.use_prev_state and self.prev_states is not None:
            prev_temp, prev_Y = self.prev_states
            prev_Y_key = np.asarray(prev_Y)
            prev_Y_key_trans = np.log10(np.maximum(np.abs(prev_Y_key), 1e-20))
            
            dTdt = (np.log10(temp) - np.log10(prev_temp))
            dYdt = (Y_key_trans - prev_Y_key_trans)
            
            obs_components = np.concatenate([[T_norm], Y_key_trans, [P_norm], [dTdt], dYdt]).astype(np.float32)
        
        # Update previous state
        self.prev_states = [temp, Y_key]
        #print(f"Obs components: {obs_components}")
        return obs_components
    
    def build_subsampled(
        self,
        trajectory: np.ndarray,
        solver_sequence: List[str],
        pressure: float,
        n_samples: int = 100,
        balance_strategy: str = "proportional_cap",
        rng_seed: Optional[int] = None,
        no_reaction_tol: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray, bool]:
        """
        Build observations for a *subsampled* subset of the trajectory,
        returning balanced (X, y) ready for supervised learning.

        Because ObservationBuilder is stateful (prev_state tracking), we walk
        the full trajectory sequentially but only *keep* the selected indices.

        **No-reaction detection**: if the temperature at the first and last
        trajectory points differ by less than ``no_reaction_tol`` Kelvin, the
        case is considered non-reactive and only a single sample is returned
        (the first step).  The third return value flags this.

        Parameters
        ----------
        trajectory : np.ndarray, shape (T+1, state_dim)
            Full state trajectory (including the initial state at index 0).
            trajectory[0] is the initial state, trajectory[1:] correspond to
            the integration steps.
        solver_sequence : list[str], length T
            Solver label for each integration step (len == trajectory.shape[0]-1).
        pressure : float
            Pressure in Pa (needed by ``build``).
        n_samples : int
            Target number of (obs, action) pairs to keep.
        balance_strategy : str
            ``"proportional_cap"`` – keep original class proportions but cap the
            total at *n_samples*.  Each class contributes at most
            ``n_samples // n_classes`` samples; leftover budget is given to the
            larger class.  This prevents the minority class from being drowned
            out when one solver dominates (e.g. 80 % QSS / 20 % CVODE).
            ``"equal"`` – sample an equal number from each class.
        rng_seed : int | None
            Seed for reproducible sampling.
        no_reaction_tol : float
            Temperature tolerance (K) for detecting non-reactive trajectories.

        Returns
        -------
        X : np.ndarray, shape (n_kept, obs_dim)
        y : np.ndarray, shape (n_kept,), dtype int8   (0=CVODE, 1=QSS)
        no_reaction : bool
            True if the trajectory was detected as non-reactive.
        """
        rng = np.random.default_rng(rng_seed)

        T = len(solver_sequence)
        assert trajectory.shape[0] == T + 1, (
            f"trajectory length {trajectory.shape[0]} != solver_sequence "
            f"length {T} + 1"
        )

        # --- encode actions ---
        solver_map = {"CVODE": 0, "QSS": 1}
        actions = np.array(
            [solver_map.get(s.split("->")[0], 0) for s in solver_sequence],
            dtype=np.int8,
        )

        # --- no-reaction check ---
        T_init = trajectory[0, 0]
        T_final = trajectory[-1, 0]
        no_reaction = abs(T_final - T_init) < no_reaction_tol

        if no_reaction:
            # Only keep one sample: the first step
            self.reset(trajectory[0])
            obs = self.build(states=trajectory[0], pressure=pressure)
            X = obs.reshape(1, -1).astype(np.float32)
            y = actions[:1]
            return X, y, True

        # --- decide which indices to keep (class-balanced) ---
        classes = np.unique(actions)
        n_classes = len(classes)

        per_class_indices = {c: np.where(actions == c)[0] for c in classes}

        if balance_strategy == "equal":
            per_class_budget = n_samples // n_classes
            chosen = []
            for c in classes:
                idx_c = per_class_indices[c]
                k = min(per_class_budget, len(idx_c))
                chosen.append(rng.choice(idx_c, size=k, replace=False))
            chosen = np.concatenate(chosen)

        elif balance_strategy == "proportional_cap":
            # Each class gets budget proportional to its share, but the
            # minority class is guaranteed at least n_samples // n_classes
            # slots (unless it has fewer points).
            min_budget = n_samples // n_classes
            chosen = []
            remaining_budget = n_samples
            # first pass: guarantee minority classes their share
            class_budgets = {}
            for c in sorted(classes, key=lambda c: len(per_class_indices[c])):
                idx_c = per_class_indices[c]
                budget = min(min_budget, len(idx_c))
                class_budgets[c] = budget
                remaining_budget -= budget
            # second pass: distribute leftover to larger classes
            for c in sorted(classes, key=lambda c: len(per_class_indices[c]),
                            reverse=True):
                idx_c = per_class_indices[c]
                extra = min(remaining_budget, len(idx_c) - class_budgets[c])
                extra = max(0, extra)
                class_budgets[c] += extra
                remaining_budget -= extra
            for c in classes:
                idx_c = per_class_indices[c]
                k = min(class_budgets[c], len(idx_c))
                chosen.append(rng.choice(idx_c, size=k, replace=False))
            chosen = np.concatenate(chosen)

        else:
            raise ValueError(f"Unknown balance_strategy: {balance_strategy}")

        chosen_set = set(chosen.tolist())

        # --- walk trajectory, build obs, keep only chosen ---
        self.reset(trajectory[0])

        X_list: List[np.ndarray] = []
        y_list: List[int] = []

        for i in range(T):
            # trajectory[i] is the state *before* step i
            obs = self.build(states=trajectory[i], pressure=pressure)
            if i in chosen_set:
                X_list.append(obs)
                y_list.append(actions[i])

        X = np.array(X_list, dtype=np.float32)
        y = np.array(y_list, dtype=np.int8)
        return X, y, False


class AdaptiveRLStrategy(SolverStrategy):
    """Adaptive solver strategy using RL policy to select integrator."""
    
    def __init__(self, gas: ct.Solution, pressure: float, config: Dict[str, Any],
                 initial_state: np.ndarray, rl_agent, observation_builder: ObservationBuilder, confidence_threshold: float = 0.6,
                 record_decisions: bool = False):
        super().__init__()
        self.cvode = CVODEStrategy(gas, pressure, config, initial_state)
        self.qss = QSSStrategy(gas, pressure, config, initial_state)
        self.rl_agent = rl_agent
        self.obs_builder = observation_builder
        self.obs_builder.reset(initial_state)
        
        self._last_solver = None
        self._last_solver_name = None
        self._last_confidence = None
        
        self.pressure = pressure
        
        self.inference_count = 0
        
        # Profiling
        self.inference_times = []
        
        self.n_steps_per_inference = config.get('num_steps', 50)
        #print(f"n_steps_per_inference: {self.n_steps_per_inference}")
        
        self.confidence_threshold = confidence_threshold

        # When True, append one dict per policy evaluation to rl_decision_log (see step()).
        self.record_decisions = record_decisions
        self.rl_decision_log: List[Dict[str, Any]] = []
        self._pending_rl_decision: Optional[Dict[str, Any]] = None
        
        self.low_confidence_steps = 0
        self.low_confidence_steps_list = []
    
    def select_solver(self, state: np.ndarray, pressure: float) -> Tuple[SolverStrategy, str, float, float]:
        """
        Select solver using RL policy with timing.
        
        Returns:
            (selected_solver, solver_name, confidence, inference_time)
        """
        obs = self.obs_builder.build(state, pressure)
        
        # Time the inference
        t_start = time.perf_counter()
        if self.record_decisions:
            action, confidence, probs, _ = self.rl_agent.select_action_detailed(
                obs, deterministic=True
            )
            inference_time = time.perf_counter() - t_start
            self._pending_rl_decision = {
                "step_index": int(self.inference_count),
                "obs": np.asarray(obs, dtype=np.float32).copy(),
                "policy_action": int(action),
                "policy_confidence": float(confidence),
                "probs": np.asarray(probs, dtype=np.float32).copy(),
            }
        else:
            action, confidence, _ = self.rl_agent._select_action(obs)
            inference_time = time.perf_counter() - t_start
        #print(f"Action: {action} - Confidence: {confidence}")
        
        self.inference_times.append(inference_time)
        
        use_qss = bool(action)
        solver = self.qss if use_qss else self.cvode
        solver_name = 'QSS' if use_qss else 'CVODE'
        
        self._last_solver_name = solver_name
        self._last_solver = solver
        self._last_confidence = confidence
 
        return solver, solver_name, confidence, inference_time
    
    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        """Execute one timestep with RL-selected solver and fallback logic."""
        if self.inference_count % self.n_steps_per_inference == 0:
            primary, primary_name, confidence, inf_time = self.select_solver(state, self.pressure)
            # if confidence is less than confidence threshold, use fallback solver (CVODE)
            if confidence < self.confidence_threshold:
                #print(f"{primary_name} chosen but Confidence {confidence} is less than confidence threshold {self.confidence_threshold}, for step {self.inference_count}, using fallback solver (CVODE)")
                primary = self.cvode
                primary_name = 'CVODE'
                self.low_confidence_steps += 1
                self.low_confidence_steps_list.append(self.inference_count)
            if self.record_decisions and self._pending_rl_decision is not None:
                pend = self._pending_rl_decision
                self._pending_rl_decision = None
                executed = 0 if primary_name == 'CVODE' else 1
                self.rl_decision_log.append({**pend, "executed_action": executed})
        else:
            primary = self._last_solver
            primary_name = self._last_solver_name
        
        self.inference_count += 1
        fallback = self.qss if primary_name == 'CVODE' else self.cvode
        fallback_name = 'QSS' if primary_name == 'CVODE' else 'CVODE'
        
        # Try primary solver
        new_state, success, cpu_time, _ = primary.step(state, dt)
        
        if success:
            return new_state, True, cpu_time, primary_name
        
        # Fallback to alternative solver
        new_state_fb, success_fb, cpu_time_fb, _ = fallback.step(state, dt)
        total_cpu = cpu_time + cpu_time_fb
        solver_used = f'{primary_name}->{fallback_name}'
        
        if success_fb:
            return new_state_fb, True, total_cpu, solver_used
        
        # Both solvers failed
        return state, False, total_cpu, solver_used


class HeuristicSolverStrategy(SolverStrategy):
    """Generic heuristic-based strategy that can use any user-provided rule."""

    def __init__(
        self,
        gas: ct.Solution,
        pressure: float,
        config: Dict[str, Any],
        initial_state: np.ndarray,
        heuristic_fn: Optional[Callable[[np.ndarray, float, int], str]] = None,
    ):
        """
        Parameters
        ----------
        heuristic_fn : callable or None
            Function ``f(state, dt, step_index) -> str`` returning either
            'CVODE' or 'QSS' (case-insensitive). If None, a simple temperature
            threshold heuristic is used.
        """
        self.cvode = CVODEStrategy(gas, pressure, config, initial_state)
        self.qss = QSSStrategy(gas, pressure, config, initial_state)
        self.heuristic_fn = heuristic_fn
        self.step_index = 0

        # Default heuristic parameters (used if heuristic_fn is None)
        self.default_T_threshold = config.get("heuristic_T_threshold", 1100.0)

    def _default_heuristic(self, state: np.ndarray, dt: float, step_index: int) -> str:
        T = float(state[0])
        return "CVODE" if T <= self.default_T_threshold else "QSS"

    def _choose_solvers(self, state: np.ndarray, dt: float) -> Tuple[SolverStrategy, SolverStrategy, str]:
        if self.heuristic_fn is None:
            name = self._default_heuristic(state, dt, self.step_index)
        else:
            name = self.heuristic_fn(state, dt, self.step_index)

        name_upper = str(name).upper()
        if name_upper == "QSS":
            primary = self.qss
            fallback = self.cvode
        else:
            primary = self.cvode
            fallback = self.qss
            name_upper = "CVODE"
        return primary, fallback, name_upper

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        primary, fallback, primary_name = self._choose_solvers(state, dt)
        self.step_index += 1

        new_state, ok, cpu, used = primary.step(state, dt)
        if ok:
            return new_state, True, cpu, primary_name

        new_state_fb, ok_fb, cpu_fb, _ = fallback.step(state, dt)
        total_cpu = cpu + cpu_fb
        solver_used = f"{primary_name}->{ 'QSS' if primary_name == 'CVODE' else 'CVODE'}"
        return (new_state_fb if ok_fb else state), ok_fb, total_cpu, solver_used


def _build_supervised_features(
    state: np.ndarray,
    *,
    n_species: int,
    pressure_pa: float,
    dt_value: float,
    pressure_unit: str,
    input_mode: str,
    h2o2_species_indices: Optional[List[int]],
) -> np.ndarray:
    """
    Build the feature vector X for the supervised nets from a single state.

    Mirrors the logic in train_supervised_nets.build_features_and_targets for X.
    """
    T = np.array([[float(state[0])]], dtype=np.float32)
    P = np.array([[float(pressure_pa)]], dtype=np.float32)
    Y = np.array(state[1 : 1 + n_species], dtype=np.float32).reshape(1, -1)

    if pressure_unit == "bar":
        P = P / 101325.0

    Y_clip = np.clip(Y, EPS_Y, 1.0)
    logY = np.log10(Y_clip).astype(np.float32)

    logdt = np.log10(np.array([[dt_value]], dtype=np.float32))

    if input_mode == "full":
        X = np.concatenate([logY, T, P, logdt], axis=1)
    else:
        assert h2o2_species_indices is not None, "h2o2_species_indices required for input_mode='h2o2_12'"
        X = np.concatenate([logY[:, h2o2_species_indices], T, P, logdt], axis=1)
    return X.astype(np.float32)


def _choose_integrator_from_predictions(cpu: np.ndarray, err: np.ndarray, thr: float) -> int:
    """
    cpu, err: shape (2,) for [CVODE, QSS].
    Returns chosen integrator index using the same rule as the paper:
      - Among integrators with err <= thr, choose min cpu
      - If none feasible, choose min err
    """
    feas = err <= thr
    if np.any(feas):
        return int(np.argmin(np.where(feas, cpu, np.inf)))
    return int(np.argmin(err))


class SupervisedMLStrategy(SolverStrategy):
    """
    Strategy that uses the trained supervised nets (CPU + error) to select
    between CVODE and QSS at each step.
    """

    def __init__(
        self,
        gas: ct.Solution,
        pressure: float,
        config: Dict[str, Any],
        initial_state: np.ndarray,
        model_dir: Path,
        error_threshold: float = 1e-5,
        device: str = "cpu",
    ):
        self.cvode = CVODEStrategy(gas, pressure, config, initial_state)
        self.qss = QSSStrategy(gas, pressure, config, initial_state)
        self.pressure_pa = float(pressure)
        self.error_threshold = float(error_threshold)
        self.device = torch.device(device)

        # Load metadata + normalizer
        meta = json.loads((model_dir / "meta.json").read_text())
        norm = np.load(model_dir / "normalizer.npz")
        self.x_mean = norm["mean"].astype(np.float32)
        self.x_std = norm["std"].astype(np.float32)

        self.n_species = int(meta["n_species"])
        self.input_dim = int(meta["input_dim"])
        self.dt_value = float(meta["dt"])
        self.pressure_unit = str(meta["pressure_unit"])
        self.alpha_T = float(meta["alpha_T"])
        self.alpha_Y = float(meta["alpha_Y"])
        self.input_mode = str(meta["input_mode"])
        self.h2o2_species_indices = meta.get("h2o2_species_indices", None)

        # Instantiate and load networks
        self.cpu_net = MLP(self.input_dim, hidden=[256, 256, 256, 256, 128], out_dim=2).to(self.device)
        self.err_net = MLP(self.input_dim, hidden=[1024, 512, 256], out_dim=2).to(self.device)

        cpu_ckpt = torch.load(model_dir / "cpu_net.pt", map_location=self.device)
        err_ckpt = torch.load(model_dir / "err_net.pt", map_location=self.device)
        self.cpu_net.load_state_dict(cpu_ckpt["state_dict"], strict=True)
        self.err_net.load_state_dict(err_ckpt["state_dict"], strict=True)

        self.cpu_net.eval()
        self.err_net.eval()

        self.inference_count = 0
        self.last_choice = None
        
        # Profiling
        self.inference_times: List[float] = []

    def _predict_cpu_and_error(self, state: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        X = _build_supervised_features(
            state,
            n_species=self.n_species,
            pressure_pa=self.pressure_pa,
            dt_value=self.dt_value,
            pressure_unit=self.pressure_unit,
            input_mode=self.input_mode,
            h2o2_species_indices=self.h2o2_species_indices,
        )
        Xn = (X - self.x_mean) / self.x_std

        x_t = torch.from_numpy(Xn).to(self.device)
        t0 = time.perf_counter()
        with torch.no_grad():
            cpu_pred = self.cpu_net(x_t).detach().cpu().numpy()[0]
            logerr_pred = self.err_net(x_t).detach().cpu().numpy()[0]
        t1 = time.perf_counter()
        self.inference_times.append(t1 - t0)

        err_pred = np.maximum(10.0 ** logerr_pred, EPS_ERR)
        return cpu_pred.astype(float), err_pred.astype(float)

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        self.inference_count += 1
        if self.inference_count % 50 == 0:
            cpu_pred, err_pred = self._predict_cpu_and_error(state)
            choice = _choose_integrator_from_predictions(cpu_pred, err_pred, self.error_threshold)
            self.last_choice = choice
        else:
            choice = self.last_choice
        primary = self.cvode if choice == 0 else self.qss
        fallback = self.qss if choice == 0 else self.cvode
        primary_name = "CVODE" if choice == 0 else "QSS"    

        new_state, ok, cpu, used = primary.step(state, dt)
        if ok:
            return new_state, True, cpu, primary_name

        new_state_fb, ok_fb, cpu_fb, _ = fallback.step(state, dt)
        total_cpu = cpu + cpu_fb
        solver_used = f"{primary_name}->{ 'QSS' if primary_name == 'CVODE' else 'CVODE'}"
        return (new_state_fb if ok_fb else state), ok_fb, total_cpu, solver_used

class PlotStyler:
    """Manages plot styling and appearance."""
    
    def __init__(self):
        """Initialize with high-quality plotting parameters."""
        try:
            plt.style.use('seaborn-v0_8-darkgrid')
        except:
            plt.style.use('seaborn-darkgrid')
        
        try:
            sns.set_palette("husl")
        except:
            pass
        
        plt.rcParams.update({
            'font.size': 16,
            'font.weight': 'bold',
            'axes.linewidth': 3,
            'lines.linewidth': 4,
            'grid.alpha': 0.4,
            'figure.dpi': 150,
            'savefig.dpi': 300,
            'axes.labelweight': 'bold',
            'axes.titleweight': 'bold',
            'legend.fontsize': 14,
            'legend.framealpha': 0.9
        })
    
    def get_colors(self, n_methods):
        """Get distinct colors for different methods."""
        colors = ['blue', 'red', 'green', 'black']
        return colors[:n_methods]
    
    def get_line_styles(self, n_methods):
        """Get distinct line styles for different methods."""
        linestyles = ['-', ':', '--', '-.']
        return linestyles[:n_methods]
    
    
@dataclass
class ProfilingResult:
    """Results with detailed profiling information."""
    trajectory: Optional[np.ndarray]
    times: Optional[np.ndarray]
    final_state: np.ndarray
    cpu_time: float
    cpu_trajectory: List[float]
    solver_sequence: List[str]
    error: Optional[float]
    ignition_delay: Optional[float]
    success: bool
    inference_times: List[float] = field(default_factory=list)
    wall_time: float = 0.0  # Elapsed wall-clock time (s) for the full run
    
    @property
    def num_steps(self) -> int:
        """Number of successful integration steps."""
        return len(self.cpu_trajectory)
    
    @property
    def avg_step_time(self) -> float:
        """Average CPU time per step."""
        return self.cpu_time / max(1, self.num_steps)
    
    @property
    def total_inference_time(self) -> float:
        """Total inference time for RL agent."""
        return sum(self.inference_times) if self.inference_times else 0.0
    
    @property
    def avg_inference_time(self) -> float:
        """Average inference time per step."""
        return self.total_inference_time / max(1, len(self.inference_times))
    
    def get_solver_usage(self) -> Dict[str, int]:
        """Count usage of each solver."""
        usage = {}
        for solver in self.solver_sequence:
            usage[solver] = usage.get(solver, 0) + 1
        return usage

from tqdm import tqdm

class ProfilingEvaluator:
    """Evaluator with detailed profiling capabilities."""
    
    def __init__(self, config: EvaluationConfig):
        self.config = config
    
    def evaluate(self, strategy: SolverStrategy, initial_state: np.ndarray,
                 reference_trajectory: Optional[np.ndarray] = None) -> ProfilingResult:
        """Run evaluation with detailed profiling."""
        n_steps = int(np.ceil(self.config.t_end / self.config.dt))
        #print(f"Evaluating strategy {strategy.__class__.__name__} with t_end: {self.config.t_end} and dt: {self.config.dt} - number of steps: {n_steps}")
        
        current_state = initial_state.copy()
        
        # Initialize recording
        states = [current_state.copy()] if self.config.record_trajectory else []
        times = [0.0] if self.config.record_trajectory else []
        cpu_trajectory = []
        solver_sequence = []
        
        t = 0.0
        total_cpu = 0.0
        success = True
        
        temp = current_state[0]
        ignition_tracker = 0
        
        # Integration loop with timing
        wall_time_start = time.perf_counter()
        
        with tqdm(total=n_steps, desc=f"Evaluating strategy {strategy.__class__.__name__}") as pbar:
            for step in range(n_steps):
                new_state, ok, cpu_time, solver_used = strategy.step(current_state, self.config.dt)
                temp = new_state[0]
                if temp > 1600:
                    ignition_tracker += 1
                
                total_cpu += cpu_time
                cpu_trajectory.append(cpu_time)
                solver_sequence.append(solver_used)
                
                if not ok:
                    success = False
                    break
                
                current_state = new_state
                t += self.config.dt
                
                if self.config.record_trajectory:
                    states.append(current_state.copy())
                    times.append(t)
                    
                # if ignition_tracker > 1000:
                #     print(f"Steady state reached at {t} seconds with temperature {temp:.1f}K")
                #     success = True
                #     break
                
                pbar.set_postfix(cpu_time=f"{total_cpu:.6f}s", success=f"{'✓' if success else '✗'}", solver_used=solver_used, T=f"{current_state[0]:.1f}K")
                pbar.update(1)
        
        wall_time = time.perf_counter() - wall_time_start
        
        # Compute metrics
        trajectory = np.array(states) if self.config.record_trajectory else None
        times_array = np.array(times) if self.config.record_trajectory else None
        
        error = self._compute_error(trajectory, reference_trajectory) if trajectory is not None else None
        ignition_delay = self._compute_ignition_delay(trajectory, self.config.dt, 
                                                      self.config.t_end) if trajectory is not None else None
        
        # Get inference times if available
        inference_times = []
        if hasattr(strategy, 'inference_times'):
            inference_times = strategy.inference_times.copy()
        
        return ProfilingResult(
            trajectory=trajectory,
            times=times_array,
            final_state=current_state,
            cpu_time=total_cpu,
            cpu_trajectory=cpu_trajectory,
            solver_sequence=solver_sequence,
            error=error,
            ignition_delay=ignition_delay,
            success=success,
            inference_times=inference_times,
            wall_time=wall_time,
        )
    
    def _compute_error(self, trajectory: np.ndarray, 
                       reference: Optional[np.ndarray]) -> Optional[float]:
        """Compute trajectory error against reference solution."""
        if reference is None or trajectory is None:
            return None
        
        min_len = min(len(trajectory), len(reference))
        diff = trajectory[:min_len] - reference[:min_len]
        return float(np.linalg.norm(diff) / min_len)
    
    def _compute_ignition_delay(self, trajectory: np.ndarray, dt: float, 
                                t_end: float) -> Optional[float]:
        """Compute ignition delay from temperature trajectory."""
        if trajectory is None:
            return None
        
        temps = trajectory[:, 0]
        
        if len(temps) < 2:
            return None
        
        dT_dt = np.diff(temps) / dt
        ignition_idx = np.argmax(dT_dt)
        
        return float(ignition_idx * dt)

class CompletePipeline:
    """Complete evaluation pipeline for combustion solver comparison."""
    
    def __init__(
        self,
        mechanism: str,
        condition: Dict[str, Any],
        config: Dict[str, Any],
        rl_selector,
        supervised_model_dir: Optional[str] = None,
        supervised_error_threshold: float = 1e-5,
        supervised_device: str = "cpu",
        heuristic_fn: Optional[Callable[[np.ndarray, float, int], str]] = None,
        heuristic_fns: Optional[Dict[str, Callable[[np.ndarray, float, int], str]]] = None,
        confidence_threshold: float = 0.6,
        record_rl_decisions: bool = False,
    ):
        """
        Initialize the complete pipeline.
        
        Args:
            mechanism: Path to Cantera mechanism file
            condition: Dictionary with temp, pressure, Z, fuel, oxidizer, dt, t_end, key_species
            config: Solver configuration dictionary
            rl_selector: RL agent for adaptive strategy
            heuristic_fn: Single heuristic function (backward-compat). Ignored
                when *heuristic_fns* is provided.
            heuristic_fns: Dict mapping display names (e.g. "H-Gradient") to
                heuristic callables ``f(state, dt, step_idx) -> str``.
        """
        self.mechanism = mechanism
        self.condition = condition
        self.config = config
        self.rl_selector = rl_selector
        self.supervised_model_dir = Path(supervised_model_dir) if supervised_model_dir is not None else None
        self.supervised_error_threshold = float(supervised_error_threshold)
        self.supervised_device = supervised_device
        self.heuristic_fn = heuristic_fn
        self.heuristic_fns: Dict[str, Callable] = heuristic_fns or {}
        self.confidence_threshold = confidence_threshold
        self.record_rl_decisions = record_rl_decisions
        # Initialize state
        self.initial_state = self._initialize_state()
        
        print(f"Config: {config}")
        
        # Setup evaluation config
        self.eval_config = EvaluationConfig(
            dt=condition['dt'],
            t_end=condition['t_end'],
            pressure=condition['pressure'],
            record_trajectory=True,
            use_old_observation=False,
            use_prev_state=config.get('use_prev_state', True),
            use_gradient_only=config.get('use_gradient_only', False)
        )
        
        # Initialize evaluator
        self.evaluator = ProfilingEvaluator(self.eval_config)
        
        # Setup observation builder
        gas = ct.Solution(mechanism)
        self.species_indices = [gas.species_index(sp) for sp in condition['key_species']]
        
        # Initialize plot styler
        self.styler = PlotStyler()
        
        # print(f"Pipeline initialized:")
        # print(f"  Mechanism: {mechanism}")
        # print(f"  Temperature: {condition['temp']} K")
        # print(f"  Pressure: {condition['pressure']/ct.one_atm:.1f} atm")
        # print(f"  Time step: {condition['dt']} s")
        # print(f"  End time: {condition['t_end']} s")
        # print(f"  Species tracked: {len(self.species_indices)}")
    
    def _initialize_state(self) -> np.ndarray:
        """Initialize thermochemical state from condition."""
        gas = ct.Solution(self.mechanism)
        if 'phi' in self.condition:
            gas.set_equivalence_ratio(
                self.condition['phi'], 
                self.condition['fuel'], 
                self.condition['oxidizer']
            )
        elif 'Z' in self.condition:
            gas.set_mixture_fraction(
                self.condition['Z'], 
                self.condition['fuel'], 
                self.condition['oxidizer']
            )
        else:
            print("No phi or Z in condition, using equivalence ratio 1")
            gas.set_equivalence_ratio(
                1, 
                self.condition['fuel'], 
                self.condition['oxidizer']
            )
        gas.TP = self.condition['temp'], self.condition['pressure']
        return np.hstack([gas.T, gas.Y])
    
    def _initialize_strategies(self) -> Dict[str, SolverStrategy]:
        """Initialize all solver strategies."""
        strategies = {}
        
        # CVODE strategy
        strategies['CVODE'] = CVODEStrategy(
            ct.Solution(self.mechanism),
            self.condition['pressure'],
            self.config,
            self.initial_state.copy(),
            method='cvode'
        )
        
        # strategies['CVODE-Sundials'] = CVODEStrategy(
        #     ct.Solution(self.mechanism),
        #     self.condition['pressure'],
        #     self.config,
        #     self.initial_state.copy(),
        #     cvode_method='cvode'
        # )
        
        # QSS strategy
        strategies['QSS'] = QSSStrategy(
            ct.Solution(self.mechanism),
            self.condition['pressure'],
            self.config,
            self.initial_state.copy()
        )
        
        # RL-Adaptive strategy
        obs_builder = ObservationBuilder(
            species_indices=self.species_indices,
            use_old_observation=False,
            use_gradient_only=self.config.get('use_gradient_only', False),
            use_prev_state=self.config.get('use_prev_state', True)
        )
        
        strategies['RL-Adaptive'] = AdaptiveRLStrategy(
            ct.Solution(self.mechanism),
            self.condition['pressure'],
            self.config,
            self.initial_state.copy(),
            self.rl_selector,
            obs_builder,
            confidence_threshold=self.confidence_threshold,
            record_decisions=self.record_rl_decisions,
        )

        # Supervised ML strategy (if model directory provided)
        if self.supervised_model_dir is not None:
            strategies['Supervised-ML'] = SupervisedMLStrategy(
                ct.Solution(self.mechanism),
                self.condition['pressure'],
                self.config,
                self.initial_state.copy(),
                model_dir=self.supervised_model_dir,
                error_threshold=self.supervised_error_threshold,
                device=self.supervised_device,
            )

        # # Heuristic strategies — multiple named heuristics or single legacy one
        # if self.heuristic_fns:
        #     for name, fn in self.heuristic_fns.items():
        #         strategies[name] = HeuristicSolverStrategy(
        #             ct.Solution(self.mechanism),
        #             self.condition['pressure'],
        #             self.config,
        #             self.initial_state.copy(),
        #             heuristic_fn=fn,
        #         )
        # else:
        #     strategies['Heuristic'] = HeuristicSolverStrategy(
        #         ct.Solution(self.mechanism),
        #         self.condition['pressure'],
        #         self.config,
        #         self.initial_state.copy(),
        #         heuristic_fn=self.heuristic_fn,
        #     )
        
        return strategies
    
    def run_all_solvers(
        self,
        generate_reference: bool = True,
        only_methods: Optional[Iterable[str]] = None,
    ) -> Dict[str, ProfilingResult]:
        """
        Run all solvers and collect results.
        
        Args:
            generate_reference: Whether to generate high-accuracy reference solution
            only_methods: If set, run only these strategy names (must exist in the
                initialized strategies, e.g. ``['RL-Adaptive']`` to skip CVODE/QSS/Sup-ML).
            
        Returns:
            Dictionary mapping solver names to ProfilingResults
        """
        print("\n" + "="*70)
        print("RUNNING ALL SOLVERS" + (f" (subset: {list(only_methods)})" if only_methods else ""))
        print("="*70 + "\n")
        
        # Generate reference solution if requested
        reference_trajectory = None
        _ref_result = None
        if generate_reference:
            print("Generating reference solution...")
            _ref_result = self._generate_reference_solution()
            reference_trajectory = _ref_result['traj']
            print(f"  Reference completed: {len(reference_trajectory)} points\n")

        # Initialize strategies
        strategies = self._initialize_strategies()

        # Run each strategy
        results = {}

        # Store reference as a ProfilingResult so callers can plot it alongside other methods
        if _ref_result is not None:
            _ref_traj = _ref_result['traj']
            results["Reference"] = ProfilingResult(
                trajectory=_ref_traj,
                times=_ref_result['times'],
                final_state=_ref_traj[-1] if _ref_traj is not None and len(_ref_traj) else np.array([]),
                cpu_time=_ref_result.get('cpu_time', 0.0),
                cpu_trajectory=_ref_result.get('cpu_trajectory', []),
                solver_sequence=_ref_result.get('used_solvers', []),
                error=None,
                ignition_delay=_ref_result.get('ignition_delay'),
                success=True,
            )
        _fixed = {'RL-Adaptive', 'Supervised-ML', 'QSS', 'CVODE-Sundials', 'CVODE'}
        heuristic_names = sorted(k for k in strategies if k not in _fixed)
        run_order = []
        for key in ['RL-Adaptive', 'Supervised-ML'] + heuristic_names + [ 'QSS', 'CVODE-Sundials', 'CVODE']:
            if key in strategies:
                run_order.append(key)

        if only_methods is not None:
            want = set(only_methods)
            available = set(strategies.keys())
            missing = want - available
            if missing:
                raise ValueError(
                    f"only_methods contains {sorted(missing)} but those strategies were not "
                    f"initialized. Available: {sorted(available)}"
                )
            run_order = [k for k in run_order if k in want]
            if not run_order:
                raise ValueError("only_methods left an empty run list.")

        for name in run_order:
            print(f"Running {name}...")
            t_start = time.perf_counter()
            
            results[name] = self.evaluator.evaluate(
                strategies[name], 
                self.initial_state.copy(),
                reference_trajectory
            )
            
            wall_time = time.perf_counter() - t_start
            result = results[name]
            
            print(f"  Completed in {wall_time:.3f}s (wall time)")
            print(f"  CPU time: {result.cpu_time:.6f}s")
            print(f"  Steps: {result.num_steps}")
            print(f"  Success: {'✓' if result.success else '✗'}")
            
            if name == 'RL-Adaptive':
                percent_inference_time = (result.total_inference_time / result.cpu_time) * 100
                print(f"  Total inference time: {result.total_inference_time:.6f}s ({percent_inference_time:.2f}% of CPU time)")
                print(f"  Avg inference time: {result.avg_inference_time*1e6:.3f} μs/step")
                print(f"  Solver usage: {result.get_solver_usage()}")
            
            if result.error is not None:
                print(f"  Error: {result.error:.6e}")
            if result.ignition_delay is not None:
                print(f"  Ignition delay: {result.ignition_delay*1e6:.3f} μs")
            print()
        
        return results
    
    def _generate_reference_solution(self) -> np.ndarray:
        """Generate high-accuracy reference solution with Cantera integration."""
        gas = ct.Solution(self.mechanism)
        if 'phi' in self.condition:
            gas.set_equivalence_ratio(
                self.condition['phi'],
                self.condition['fuel'],
                self.condition['oxidizer'],
            )
        elif 'Z' in self.condition:
            gas.set_mixture_fraction(
                self.condition['Z'],
                self.condition['fuel'],
                self.condition['oxidizer'],
            )
        else:
            gas.set_equivalence_ratio(
                1,
                self.condition['fuel'],
                self.condition['oxidizer'],
            )

        # convert pressure to Pa
        pressure = self.condition['pressure']
        gas.TP = self.condition['temp'], pressure
        initial_state = np.hstack([gas.T, gas.Y])

        ref_strategy = ReferenceStrategy(
            gas,
            pressure,
            rtol=self.config.get('ref_rtol', 1e-10),
            atol=self.config.get('ref_atol', 1e-20),
            initial_state=initial_state,
        )
        result = integrate_loop(
            ref_strategy,
            initial_state,
            self.condition['dt'],
            self.condition['t_end'],
            record=True,
        )

    
        return result
    
    def print_summary_table(self, results: Dict[str, ProfilingResult]):
        """Print comprehensive summary table."""
        print("\n" + "="*100)
        print("COMPREHENSIVE PERFORMANCE SUMMARY")
        print("="*100)
        
        # Find baseline for speedup calculation
        baseline_cpu = results['CVODE'].cpu_time
        
        headers = ['Solver', 'CPU Time', 'Speedup', 'Inference', 'Steps', 'Error', 'Ign. Delay', 'Success']
        col_widths = [15, 12, 10, 12, 8, 12, 12, 8]
        
        # Print header
        header_line = "  ".join(h.ljust(w) for h, w in zip(headers, col_widths))
        print(header_line)
        print("-"*100)
        
        # Print each solver
        for name, result in results.items():
            speedup = baseline_cpu / result.cpu_time if result.cpu_time > 0 else float('inf')
            
            inference_str = f"{result.total_inference_time*1e3:.3f} ms" if result.inference_times else "N/A"
            error_str = f"{result.error:.3e}" if result.error is not None else "N/A"
            ign_str = f"{result.ignition_delay*1e6:.1f} μs" if result.ignition_delay is not None else "N/A"
            success_str = "✓" if result.success else "✗"
            
            row = [
                name,
                f"{result.cpu_time:.6f} s",
                f"{speedup:.2f}x",
                inference_str,
                str(result.num_steps),
                error_str,
                ign_str,
                success_str
            ]
            
            row_line = "  ".join(str(v).ljust(w) for v, w in zip(row, col_widths))
            print(row_line)
        
        print("="*100)
        
        # Additional RL-Adaptive statistics
        if 'RL-Adaptive' in results:
            rl_result = results['RL-Adaptive']
            print("\nRL-Adaptive Details:")
            print(f"  Average inference time per step: {rl_result.avg_inference_time*1e6:.3f} μs")
            print(f"  Inference overhead: {rl_result.total_inference_time/rl_result.cpu_time*100:.2f}% of CPU time")
            
            usage = rl_result.get_solver_usage()
            total = sum(usage.values())
            print(f"  Solver distribution:")
            for solver, count in sorted(usage.items()):
                print(f"    {solver}: {count} steps ({count/total*100:.1f}%)")
    
    def plot_results(self, results: Dict[str, ProfilingResult], save_dir: Optional[str] = None):
        """Generate comprehensive plots."""
        print("\nGenerating plots...")
        
        fig = plt.figure(figsize=(20, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        colors = self.styler.get_colors(len(results))
        linestyles = self.styler.get_line_styles(len(results))
        
        # 1. Temperature trajectory
        ax1 = fig.add_subplot(gs[0, :])
        for (name, result), color, ls in zip(results.items(), colors, linestyles):
            if result.trajectory is not None:
                ax1.plot(result.times * 1e6, result.trajectory[:, 0], 
                        label=name, color=color, linestyle=ls)
        ax1.set_xlabel('Time (μs)')
        ax1.set_ylabel('Temperature (K)')
        ax1.set_title('Temperature Evolution')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. CPU time comparison
        ax2 = fig.add_subplot(gs[1, 0])
        names = list(results.keys())
        cpu_times = [results[name].cpu_time for name in names]
        bars = ax2.bar(names, cpu_times, color=colors[:len(names)], alpha=0.7, edgecolor='black')
        ax2.set_ylabel('Total CPU Time (s)')
        ax2.set_title('CPU Time Comparison')
        ax2.grid(True, alpha=0.3, axis='y')
        for bar, time in zip(bars, cpu_times):
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{time:.4f}s', ha='center', va='bottom', fontsize=10)
        
        # 3. Speedup comparison
        ax3 = fig.add_subplot(gs[1, 1])
        baseline = results['CVODE'].cpu_time
        speedups = [baseline / results[name].cpu_time for name in names]
        bars = ax3.bar(names, speedups, color=colors[:len(names)], alpha=0.7, edgecolor='black')
        ax3.axhline(y=1.0, color='red', linestyle='--', linewidth=2, alpha=0.5)
        ax3.set_ylabel('Speedup vs CVODE')
        ax3.set_title('Speedup Comparison')
        ax3.grid(True, alpha=0.3, axis='y')
        for bar, speedup in zip(bars, speedups):
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{speedup:.2f}x', ha='center', va='bottom', fontsize=10)
        
        # 4. Error comparison
        ax4 = fig.add_subplot(gs[1, 2])
        names_with_error = [name for name in names if results[name].error is not None]
        if names_with_error:
            errors = [results[name].error for name in names_with_error]
            bars = ax4.bar(names_with_error, errors, alpha=0.7, edgecolor='black', color='coral')
            ax4.set_ylabel('Error (L2 Norm)')
            ax4.set_title('Accuracy Comparison')
            ax4.set_yscale('log')
            ax4.grid(True, alpha=0.3, axis='y')
        
        # 5. CPU time per step
        ax5 = fig.add_subplot(gs[2, 0])
        for (name, result), color, ls in zip(results.items(), colors, linestyles):
            if result.cpu_trajectory:
                ax5.plot(result.cpu_trajectory, label=name, color=color, 
                        linestyle=ls, alpha=0.7)
        ax5.set_xlabel('Step')
        ax5.set_ylabel('CPU Time (s)')
        ax5.set_title('CPU Time per Step')
        ax5.set_yscale('log')
        ax5.legend()
        ax5.grid(True, alpha=0.3)
        
        # 6. RL-Adaptive solver usage
        if 'RL-Adaptive' in results:
            ax6 = fig.add_subplot(gs[2, 1])
            rl_result = results['RL-Adaptive']
            usage = rl_result.get_solver_usage()
            ax6.pie(usage.values(), labels=usage.keys(), autopct='%1.1f%%',
                   startangle=90, colors=plt.cm.Set3(range(len(usage))))
            ax6.set_title('RL-Adaptive Solver Usage')
            
            # 7. Solver selection over time
            ax7 = fig.add_subplot(gs[2, 2])
            solver_map = {}
            solver_numeric = []
            for solver in rl_result.solver_sequence:
                base_solver = solver.split('->')[0]  # Get base solver
                if base_solver not in solver_map:
                    solver_map[base_solver] = len(solver_map)
                solver_numeric.append(solver_map[base_solver])
            
            ax7.plot(solver_numeric, drawstyle='steps-post', linewidth=2, color='navy')
            ax7.set_xlabel('Step')
            ax7.set_ylabel('Solver')
            ax7.set_yticks(range(len(solver_map)))
            ax7.set_yticklabels(list(solver_map.keys()))
            ax7.set_title('RL Solver Selection Timeline')
            ax7.grid(True, alpha=0.3, axis='x')
        
        plt.suptitle(f'Complete Solver Evaluation - T={self.condition["temp"]}K, P={self.condition["pressure"]/ct.one_atm:.1f}atm', 
                    fontsize=18, fontweight='bold')
        
        if save_dir:
            import os
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f'complete_evaluation_T{self.condition["temp"]}_P{self.condition["pressure"]/ct.one_atm:.0f}atm.png')
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"  Saved plot to: {save_path}")
        
        return fig
    
    def export_results(self, results: Dict[str, ProfilingResult], filename: str):
        """Export results to CSV file."""
        import csv
        import os
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow([
                'Solver', 'CPU_Time', 'Total_Inference_Time', 'Avg_Inference_Time',
                'Num_Steps', 'Avg_Step_Time', 'Error', 'Ignition_Delay', 'Success'
            ])
            
            # Write data
            for name, result in results.items():
                writer.writerow([
                    name,
                    result.cpu_time,
                    result.total_inference_time,
                    result.avg_inference_time,
                    result.num_steps,
                    result.avg_step_time,
                    result.error if result.error is not None else 'N/A',
                    result.ignition_delay if result.ignition_delay is not None else 'N/A',
                    result.success
                ])
        
        print(f"\nResults exported to: {filename}")
    
    def run_complete_evaluation(self, save_dir: Optional[str] = None, 
                               export_csv: bool = True) -> Dict[str, ProfilingResult]:
        """
        Run complete evaluation pipeline.
        
        Args:
            save_dir: Directory to save plots and results
            export_csv: Whether to export results to CSV
            
        Returns:
            Dictionary of ProfilingResults for each solver
        """
        print("\n" + "="*70)
        print("COMPLETE EVALUATION PIPELINE")
        print("="*70)
        
        # Run all solvers
        results = self.run_all_solvers(generate_reference=True)
        
        # Print summary
        self.print_summary_table(results)
        
        # Generate plots
        self.plot_results(results, save_dir=save_dir)
        
        # Export to CSV
        if export_csv:
            if save_dir:
                import os
                os.makedirs(save_dir, exist_ok=True)
                file_name = f'evaluation_results_{self.condition["temp"]}K_{self.condition["pressure"]/ct.one_atm:.1f}atm_{self.condition["Z"]:.3f}.csv'
                csv_path = os.path.join(save_dir, file_name)
            else:
                file_name = f'evaluation_results.csv'
                csv_path = 'evaluation_results.csv'
            self.export_results(results, csv_path)
        
        print("\n" + "="*70)
        print("EVALUATION COMPLETE")
        print("="*70 + "\n")
        
        return results
    
    
