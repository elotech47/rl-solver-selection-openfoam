from .utils import create_solver 
import numpy as np
import cantera as ct 
import time
from datetime import datetime 
import seaborn as sns 
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List
from collections import Counter
import matplotlib.pyplot as plt

# Set up high-quality plotting parameters
plt.style.use('seaborn-v0_8-darkgrid')
sns.set_palette("husl")
plt.rcParams.update({
    'font.family': 'DejaVu Sans',
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

mechanism_options = {
    "ndodecane" : {
        "mechanism":"large_mechanism/n-dodecane.yaml",
        "fuel":"nc12h26:1.0",
        "oxidizer":"n2:3.76, o2:1.0"
    },
    "methane" : {
        "mechanism":"large_mechanism/ch4_53species.yaml",
        "fuel":"ch4:1.0",
        "oxidizer":"n2:3.76, o2:1.0"
    },
    "hydrogen" : {
        "mechanism":"h2o2.yaml",
        "fuel":"h2:1.0",
        "oxidizer":"n2:3.76, o2:1.0"
    }
}

SOLVER_CONFIG = {
    # reference integration
    "ref_rtol": 1e-10,
    "ref_atol": 1e-20,

    # solver tolerances — loosened from 1e-8/1e-12 after diagnosing stiffness
    # failures at ignition onset (900K/60atm n-decane); scipy BDF validated at these values
    "cvode_rtol": 1e-6,
    "cvode_atol": 1e-8,
    
    "qss_dtmin": 1e-12,
    "qss_dtmax": 1e-6,
    "qss_abstol": 1e-11,
    "qss_itermax": 2,
    "epsmin":0.02,
    "epsmax":100,
    "mxsteps": 100000,

    "use_prev_state": True,
    "use_gradient_only": False,
}

class SolverStrategy:
    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        """Advance one step of size dt.
        Returns: (new_state, success, cpu_time, solver_used)
        """
        raise NotImplementedError


class ReferenceStrategy(SolverStrategy):
    def __init__(self, gas: ct.Solution, pressure: float, rtol: float, atol: float, initial_state: np.array):
        self.gas = gas
        # Full TPY required: a fresh ct.Solution() has default composition; TP alone is not enough.
        T = float(initial_state[0])
        Y = np.clip(np.asarray(initial_state[1:], dtype=float), 0.0, None)
        ys = float(Y.sum())
        if ys > 1e-16:
            Y = Y / ys
        self.gas.TPY = T, pressure, Y
        self.reactor = ct.IdealGasConstPressureReactor(self.gas)
        self.sim = ct.ReactorNet([self.reactor])
        self.sim.rtol = rtol
        self.sim.atol = atol
        self._time = 0.0
        self._pressure = pressure

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        start = time.time()
        # map state -> reactor
        T = float(state[0])
        Y = np.clip(state[1:], 0.0, None)
        s = Y.sum()
        if s > 1e-16:
            Y = Y / s
        self.gas.TPY = T, self._pressure, Y
        try:
            self.sim.advance(self._time + dt)
            self._time += dt
            new_state = np.hstack([self.reactor.T, self.reactor.thermo.Y])
            cpu = time.time() - start
            return new_state, True, cpu, 'reference'
        except Exception:
            cpu = time.time() - start
            return state, False, cpu, 'reference'


class CVODEStrategy(SolverStrategy):
    def __init__(self, gas: ct.Solution, pressure: float, config: Dict[str, Any], initial_state: np.ndarray, method: str = 'cvode_scipy'):
        if method not in ['cvode_scipy', 'cvode']:
            raise ValueError(f"Invalid method: {method}")
        self.gas = gas
        self.pressure = pressure
        self.config = config
        # create once
        self.solver = create_solver(
            method,
            {
                'rtol': self.config.get('cvode_rtol', 1e-6),
                'atol': self.config.get('cvode_atol', 1e-8),
            },
            self.gas,
            initial_state,
            0.0,
            self.pressure,
            mxsteps=self.config.get('mxsteps', 100000),
        )

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        start = time.time()
        self.solver.set_state(state, 0.0)
        try:
            new_state, success, error_code = self.solver.solve_to(dt)
        except Exception:
            new_state = None
            success = False
            error_code = 1
        cpu = time.time() - start
        if new_state is None:
            return state, success, cpu, 'cvode'
        return new_state, success, cpu, 'cvode'


class QSSStrategy(SolverStrategy):
    def __init__(self, gas: ct.Solution, pressure: float, config: Dict[str, Any], initial_state: np.ndarray):
        self.gas = gas
        self.pressure = pressure
        self.config = config
        # create once
        self.qss_solver = create_solver(
            'qss',
            {
                'dtmin': self.config.get('qss_dtmin', 1e-12),
                'dtmax': self.config.get('qss_dtmax', 1e-6),
                'abstol': self.config.get('qss_abstol', 1e-8),
                'itermax': self.config.get('qss_itermax', 2),
                'stabilityCheck': self.config.get('stabilityCheck', False),
                'epsmin': self.config.get('epsmin', 0.02),
                'epsmax': self.config.get('epsmax', 100.0),
                'mxsteps': self.config.get('mxsteps', 100000),
            },
            self.gas,
            initial_state,
            0.0,
            self.pressure,
        )

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        start = time.time()
        self.qss_solver.setState(state.tolist(), 0.0)
        try:
            result = self.qss_solver.integrateToTime(dt)
        except Exception:
            result = 0
            return state, False, time.time() - start, 'qss'
        if result == 0:
            return np.array(self.qss_solver.y), True, time.time() - start, 'qss'
        return state, False, time.time() - start, 'qss'


class AdaptiveStrategy(SolverStrategy):
    def __init__(self, gas: ct.Solution, pressure: float, config: Dict[str, Any], initial_state: np.ndarray):
        self.cvode = CVODEStrategy(gas, pressure, config, initial_state)
        self.qss = QSSStrategy(gas, pressure, config, initial_state)
        self.heuristic_temp_threshold = config.get('adaptive_T_threshold', 1100.0)
        self.heuristic_dT_threshold = config.get('adaptive_dT_threshold', 25.0)  # K per step
        self._last_T: Optional[float] = None

    def step(self, state: np.ndarray, dt: float) -> Tuple[np.ndarray, bool, float, str]:
        T = float(state[0])
        dT = 0.0 if self._last_T is None else (T - self._last_T)
        use_cvode = (T <= self.heuristic_temp_threshold) #or (abs(dT) <= self.heuristic_dT_threshold)
        primary = self.cvode if use_cvode else self.qss
        fallback = self.qss if use_cvode else self.cvode

        new_state, ok, cpu, used = primary.step(state, dt)
        if not ok:
            new_state2, ok2, cpu2, used2 = fallback.step(state, dt)
            total_cpu = cpu + cpu2
            self._last_T = float(new_state2[0]) if ok2 else T
            return (new_state2 if ok2 else state), ok2, total_cpu, f'{used}->{used2}'
        self._last_T = float(new_state[0])
        return new_state, True, cpu, f'{used}'

def build_strategy(name: str, gas: ct.Solution, pressure: float, config: Dict[str, Any], initial_state: np.ndarray) -> SolverStrategy:
    if name == 'reference':
        return ReferenceStrategy(gas, pressure, rtol=config.get('ref_rtol', 1e-10), atol=config.get('ref_atol', 1e-20), initial_state=initial_state)
    if name == 'cvode':
        return CVODEStrategy(gas, pressure, config, initial_state)
    if name == 'qss':
        return QSSStrategy(gas, pressure, config, initial_state)
    if name == 'adaptive':
        return AdaptiveStrategy(gas, pressure, config, initial_state)
    raise ValueError(f"Unknown strategy name: {name}")


# def compute_ignition_delay(temps: np.ndarray, dt: float, 
#                                 t_end: float) -> Optional[float]:
#         """Compute ignition delay from temperature trajectory."""
#         if len(temps) < 2:
#             return None
#         dT_dt = np.diff(temps) / dt
#         ignition_idx = np.argmax(dT_dt)
        
#         return float(ignition_idx * dt)

# def compute_ignition_delay(temps, dt, t_end, threshold=1400.0):
#         for i, T in enumerate(temps):
#             if T >= threshold:
#                 return i * dt
#         return t_end

def compute_ignition_delay(temps: np.ndarray, dt: float, 
                            t_end: float) -> Optional[float]:
    """Compute ignition delay from temperature trajectory."""
    if temps is None:
        return None
    
    if len(temps) < 2:
        return None
    
    if (temps[-1] - temps[0]) <= 10 and temps[0] <= 1000:
        return 0.0
    
    dT_dt = np.diff(temps) / dt
    ignition_idx = np.argmax(dT_dt)
    
    id = float(ignition_idx * dt)
    # print(f"Ignition delay: {id}")
    return id

def compute_error(computed, reference, single_step: bool = False, norm: str = 'l1', verbose: bool = False):
    """
    Compute error between computed and reference arrays.

    Parameters
    ----------
    computed    : array-like
    reference   : array-like
    single_step : bool, if True compares only first element scalar vs rest as vector
    norm        : 'l1'  - Mean Absolute Error style (relative)
                  'l2'  - RMSE style (relative)
                  'mae' - Mean Absolute Error (identical to l1)
                  'mse' - Mean Squared Error (relative)
    verbose     : bool, if True prints all norm comparisons (default False to reduce noise)
    """
    computed  = np.array(computed)
    reference = np.array(reference)

    if norm not in ('l1', 'l2', 'mae', 'mse'):
        raise ValueError(f"norm must be 'l1', 'l2', 'mae', or 'mse', got '{norm}'")

    # --- Length alignment ---
    if computed.shape[0] != reference.shape[0]:
        min_len   = min(computed.shape[0], reference.shape[0])
        computed  = computed[:min_len]
        reference = reference[:min_len]

    # --- Element-wise error functions (scalar) ---
    def _abs_rel(c, r):
        """L1/MAE: relative absolute error"""
        return np.abs(c - r) / (np.abs(r) + 1e-8)

    def _sq_rel(c, r):
        """MSE: relative squared error"""
        return (c - r) ** 2 / (r ** 2 + 1e-8)

    # --- Vector error functions ---
    def _l1_vec(c, r):
        """L1 norm ratio"""
        return np.linalg.norm(c - r, ord=1) / (np.linalg.norm(r, ord=1) + 1e-10)

    def _l2_vec(c, r):
        """L2 norm ratio"""
        return np.linalg.norm(c - r, ord=2) / (np.linalg.norm(r, ord=2) + 1e-10)

    if single_step:
        # computed and reference are both 1D state vectors [T, Y_0, ..., Y_N]
        c_scalar = computed[0]
        r_scalar = reference[0]
        c_vec    = computed[1:]
        r_vec    = reference[1:]

        mae_s = _abs_rel(c_scalar, r_scalar)
        mse_s = _sq_rel(c_scalar,  r_scalar)
        l1_s  = mae_s   # identical for scalars
        l2_s  = mae_s   # identical for scalars

        mae_v = _l1_vec(c_vec, r_vec)
        mse_v = _l2_vec(c_vec, r_vec) ** 2
        l1_v  = mae_v
        l2_v  = _l2_vec(c_vec, r_vec)

    else:
        # BUG FIX: ensure computed and reference are 2D before indexing with [:, 0]
        if computed.ndim == 1:
            computed  = computed[np.newaxis, :]
        if reference.ndim == 1:
            reference = reference[np.newaxis, :]

        c_scalars = computed[:, 0]
        r_scalars = reference[:, 0]

        mae_s = np.mean(_abs_rel(c_scalars, r_scalars))
        mse_s = np.mean(_sq_rel(c_scalars,  r_scalars))
        l1_s  = mae_s
        l2_s  = np.sqrt(np.mean(_sq_rel(c_scalars, r_scalars)))  # RMSE-style

        mae_v = np.mean([_l1_vec(computed[i, 1:], reference[i, 1:]) for i in range(len(computed))])
        mse_v = np.mean([_l2_vec(computed[i, 1:], reference[i, 1:]) ** 2 for i in range(len(computed))])
        l1_v  = mae_v
        l2_v  = np.sqrt(np.mean([_l2_vec(computed[i, 1:], reference[i, 1:]) ** 2 for i in range(len(computed))]))

    # BUG FIX: print only when verbose=True to avoid log flooding during training
    if verbose:
        print(
            f"[compute_error] "
            f"MAE => scalar={mae_s:.6e}, vector={mae_v:.6e} | "
            f"MSE => scalar={mse_s:.6e}, vector={mse_v:.6e} | "
            f"L1  => scalar={l1_s:.6e},  vector={l1_v:.6e} | "
            f"L2  => scalar={l2_s:.6e},  vector={l2_v:.6e}"
        )

    results = {
        'l1':  (l1_s,  l1_v),
        'mae': (mae_s, mae_v),
        'mse': (mse_s, mse_v),
        'l2':  (l2_s,  l2_v),
    }
    return results[norm]

from tqdm import tqdm

def integrate_loop(
    strategy: SolverStrategy,
    initial_state: np.ndarray,
    dt: float,
    t_end: float,
    record: bool = True,
    reference_state = None
) -> Dict[str, Any]:
    n_steps = int(np.ceil(t_end / dt))
    current_state = initial_state.copy()
    states: List[np.ndarray] = [current_state.copy()] if record else None
    times: List[float] = [0.0] if record else None
    used_solvers: List[str] = []
    cpu_traj: List[float] = []

    t = 0.0
    total_cpu = 0.0

    # Progress bar with temperature: infer from initial_state if possible
    temp = None
    try:
        temp = current_state[0]  # Often temperature is the 0th state
    except Exception:
        pass

    desc = f"Integrating"
    if temp is not None:
        desc += f" (T={temp:.1f}K)"

    prog_iter = tqdm(range(n_steps), desc=desc, disable=True)
    for i in prog_iter:
        new_state, ok, cpu, used = strategy.step(current_state, dt)
        total_cpu += cpu
        cpu_traj.append(cpu)
        used_solvers.append(used)
        # Dynamically update temperature in tqdm desc
        if hasattr(prog_iter, 'set_postfix'):
            try:
                curr_T = new_state[0]
                prog_iter.set_postfix(T=f"{curr_T:.1f}K")
            except Exception:
                pass
        prog_iter.update(1)
        if not ok:
            break
        current_state = new_state
        t += dt
        if record:
            states.append(current_state.copy())
            times.append(t)
    
    if reference_state is not None and len(states) > 0:
        error = compute_error(np.array(states), reference_state)
    else:
        error = None
    
    ignition_delay = compute_ignition_delay(np.array(states)[:, 0], dt, t_end)
    
    result = {
        'traj': np.array(states) if record else None,
        'times': np.array(times) if record else None,
        'final_state': current_state,
        'cpu_time': total_cpu,
        'cpu_trajectory': cpu_traj,
        'used_solvers': used_solvers,
        'error': error,
        'ignition_delay': ignition_delay
    }
    return result

def prepare_case(condition: Dict[str, Any]):
    mechanism_details = mechanism_options[condition['mechanism_option']]
    mechanism_file = mechanism_details['mechanism']
    fuel = mechanism_details['fuel']
    oxidizer = mechanism_details['oxidizer']
    gas = ct.Solution(mechanism_file)
    gas.set_mixture_fraction(condition['Z'], fuel, oxidizer)
    gas.TP = condition['temp'], condition['pressure']
    state0 = np.hstack([gas.T, gas.Y])
    return gas, state0

def plot_species_and_adaptive_actions(results: Dict[str, Any], gas, condition: Dict[str, Any], 
                                       save_path: str = None):
    """
    Create a 2x2 subplot showing temperature, OH, H2 profiles and adaptive solver actions.
    
    Parameters:
    -----------
    results : dict
        Dictionary containing results from different solver strategies
    gas : ct.Solution
        Cantera gas object to get species indices
    condition : dict
        Simulation conditions
    save_path : str, optional
        Path to save the figure
    """
    # Get species indices
    try:
        oh_idx = gas.species_index('OH') + 1  # +1 because state[0] is temperature
        h2_idx = gas.species_index('H2') + 1
    except:
        # Fallback if species names are different
        species_names = [s.name.lower() for s in gas.species()]
        oh_idx = next((i+1 for i, name in enumerate(species_names) if 'oh' in name), None)
        h2_idx = next((i+1 for i, name in enumerate(species_names) if 'h2' == name), None)
    
    # Set up the figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'Combustion Simulation: T={condition["temp"]:.0f}K, P={condition["pressure"]/ct.one_atm:.1f}bar, Z={condition["Z"]:.2f}', 
                 fontsize=20, fontweight='bold', y=0.995)
    
    # Define colors and styles for each mode
    colors = {'reference': '#2E86AB', 'cvode': '#A23B72', 'qss': '#F18F01', 'adaptive': '#C73E1D'}
    linestyles = {'reference': '-', 'cvode': '--', 'qss': '-.', 'adaptive': ':'}
    linewidths = {'reference': 3.5, 'cvode': 3.0, 'qss': 3.0, 'adaptive': 3.5}
    
    modes = ['reference', 'cvode', 'qss', 'adaptive']
    
    # ==================== Plot 1: Temperature Profile ====================
    ax1 = axes[0, 0]
    for mode in modes:
        if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
            times_ms = results[mode]['times'] * 1000  # Convert to milliseconds
            temps = results[mode]['traj'][:, 0]
            ax1.plot(times_ms, temps, label=mode.capitalize(), 
                    color=colors[mode], linestyle=linestyles[mode], 
                    linewidth=linewidths[mode], alpha=0.9)
            
            # Mark endpoint if simulation ended early
            if results[mode]['times'][-1] < condition['t_end'] * 0.99:
                ax1.scatter(times_ms[-1], temps[-1], marker='X', s=200, 
                           color=colors[mode], edgecolors='black', linewidths=2, 
                           zorder=10, label=f'{mode} (stopped)')
    
    ax1.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
    ax1.set_ylabel('Temperature (K)', fontsize=16, fontweight='bold')
    ax1.set_title('(a) Temperature Evolution', fontsize=17, fontweight='bold', pad=10)
    ax1.legend(loc='best', framealpha=0.95, fontsize=13)
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
    ax1.tick_params(labelsize=13, width=2, length=6)
    for spine in ax1.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 2: OH Profile ====================
    ax2 = axes[0, 1]
    if oh_idx is not None:
        for mode in modes:
            if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
                times_ms = results[mode]['times'] * 1000
                oh_mass_frac = results[mode]['traj'][:, oh_idx]
                ax2.plot(times_ms, oh_mass_frac, label=mode.capitalize(),
                        color=colors[mode], linestyle=linestyles[mode],
                        linewidth=linewidths[mode], alpha=0.9)
        
        ax2.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax2.set_ylabel('OH Mass Fraction', fontsize=16, fontweight='bold')
        ax2.set_title('(b) OH Radical Profile', fontsize=17, fontweight='bold', pad=10)
        ax2.legend(loc='best', framealpha=0.95, fontsize=13)
        ax2.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
        ax2.ticklabel_format(style='scientific', axis='y', scilimits=(0,0))
        ax2.tick_params(labelsize=13, width=2, length=6)
    else:
        ax2.text(0.5, 0.5, 'OH species not found', ha='center', va='center',
                fontsize=16, transform=ax2.transAxes)
    
    for spine in ax2.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 3: H2 Profile ====================
    ax3 = axes[1, 0]
    if h2_idx is not None:
        for mode in modes:
            if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
                times_ms = results[mode]['times'] * 1000
                h2_mass_frac = results[mode]['traj'][:, h2_idx]
                ax3.plot(times_ms, h2_mass_frac, label=mode.capitalize(),
                        color=colors[mode], linestyle=linestyles[mode],
                        linewidth=linewidths[mode], alpha=0.9)
        
        ax3.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax3.set_ylabel(r'H$_2$ Mass Fraction', fontsize=16, fontweight='bold')
        ax3.set_title('(c) Hydrogen Profile', fontsize=17, fontweight='bold', pad=10)
        ax3.legend(loc='best', framealpha=0.95, fontsize=13)
        ax3.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
        ax3.ticklabel_format(style='scientific', axis='y', scilimits=(0,0))
        ax3.tick_params(labelsize=13, width=2, length=6)
    else:
        ax3.text(0.5, 0.5, 'H2 species not found', ha='center', va='center',
                fontsize=16, transform=ax3.transAxes)
    
    for spine in ax3.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 4: Adaptive Solver Actions ====================
    ax4 = axes[1, 1]
    if 'adaptive' in results and results['adaptive']['used_solvers']:
        times_ms = results['adaptive']['times'] * 1000
        used_solvers = results['adaptive']['used_solvers']
        
        # Parse solver actions (handle fallback cases like 'cvode->qss')
        solver_timeline = []
        for action in used_solvers:
            if '->' in action:
                # Fallback occurred, use the second solver
                solver_timeline.append(action.split('->')[-1])
            else:
                solver_timeline.append(action)
        
        # Create numerical representation for plotting
        solver_map = {'cvode': 1, 'qss': 2}
        solver_numbers = [solver_map.get(s, 0) for s in solver_timeline]
        
        # Plot as step function
        ax4.step(times_ms, solver_numbers, where='post', linewidth=3.5, 
                color='#2E86AB', alpha=0.8)
        ax4.fill_between(times_ms, solver_numbers, step='post', alpha=0.3, color='#2E86AB')
        
        # Customize y-axis
        ax4.set_yticks([1, 2])
        ax4.set_yticklabels(['CVODE', 'QSS'], fontsize=14, fontweight='bold')
        ax4.set_ylim([0.5, 2.5])
        
        ax4.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax4.set_ylabel('Active Solver', fontsize=16, fontweight='bold')
        ax4.set_title('(d) Adaptive Solver Selection', fontsize=17, fontweight='bold', pad=10)
        ax4.grid(True, alpha=0.3, linestyle='--', linewidth=1.5, axis='x')
        ax4.tick_params(labelsize=13, width=2, length=6)
        
        # Add transition count annotation
        transitions = sum(1 for i in range(len(solver_timeline)-1) 
                         if solver_timeline[i] != solver_timeline[i+1])
        ax4.text(0.98, 0.97, f'Transitions: {transitions}', 
                transform=ax4.transAxes, fontsize=13, fontweight='bold',
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    else:
        ax4.text(0.5, 0.5, 'Adaptive solver data not available', 
                ha='center', va='center', fontsize=16, transform=ax4.transAxes)
    
    for spine in ax4.spines.values():
        spine.set_linewidth(2)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"Figure saved to {save_path}")
    
    plt.show()

def plot_species_and_adaptive_actions(results: Dict[str, Any], gas, condition: Dict[str, Any], 
                                       save_path: str = None):
    """
    Create a 2x2 subplot showing temperature, OH, H2 profiles and adaptive solver actions.
    
    Parameters:
    -----------
    results : dict
        Dictionary containing results from different solver strategies
    gas : ct.Solution
        Cantera gas object to get species indices
    condition : dict
        Simulation conditions
    save_path : str, optional
        Path to save the figure
    """
    # Get species indices
    try:
        oh_idx = gas.species_index('OH') + 1  # +1 because state[0] is temperature
        h2_idx = gas.species_index('H2') + 1
    except:
        # Fallback if species names are different
        species_names = [s.name.lower() for s in gas.species()]
        oh_idx = next((i+1 for i, name in enumerate(species_names) if 'oh' in name), None)
        h2_idx = next((i+1 for i, name in enumerate(species_names) if 'h2' == name), None)
    
    # Set up the figure
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'Combustion Simulation: T={condition["temp"]:.0f}K, P={condition["pressure"]/ct.one_atm:.1f}bar, Z={condition["Z"]:.2f}', 
                 fontsize=20, fontweight='bold', y=0.995)
    
    # Define colors and styles for each mode
    colors = {'reference': '#2E86AB', 'cvode': '#A23B72', 'qss': '#F18F01', 'adaptive': '#C73E1D'}
    linestyles = {'reference': '-', 'cvode': '--', 'qss': '-.', 'adaptive': ':'}
    linewidths = {'reference': 3.5, 'cvode': 3.0, 'qss': 3.0, 'adaptive': 3.5}
    
    modes = ['reference', 'cvode', 'qss', 'adaptive']
    
    # ==================== Plot 1: Temperature Profile ====================
    ax1 = axes[0, 0]
    for mode in modes:
        if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
            times_ms = results[mode]['times'] * 1000  # Convert to milliseconds
            temps = results[mode]['traj'][:, 0]
            ax1.plot(times_ms, temps, label=mode.capitalize(), 
                    color=colors[mode], linestyle=linestyles[mode], 
                    linewidth=linewidths[mode], alpha=0.9)
            
            # Mark endpoint if simulation ended early
            if results[mode]['times'][-1] < condition['t_end'] * 0.99:
                ax1.scatter(times_ms[-1], temps[-1], marker='X', s=200, 
                           color=colors[mode], edgecolors='black', linewidths=2, 
                           zorder=10, label=f'{mode} (stopped)')
    
    ax1.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
    ax1.set_ylabel('Temperature (K)', fontsize=16, fontweight='bold')
    ax1.set_title('(a) Temperature Evolution', fontsize=17, fontweight='bold', pad=10)
    ax1.legend(loc='best', framealpha=0.95, fontsize=13)
    ax1.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
    ax1.tick_params(labelsize=13, width=2, length=6)
    for spine in ax1.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 2: OH Profile ====================
    ax2 = axes[0, 1]
    if oh_idx is not None:
        for mode in modes:
            if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
                times_ms = results[mode]['times'] * 1000
                oh_mass_frac = results[mode]['traj'][:, oh_idx]
                ax2.plot(times_ms, oh_mass_frac, label=mode.capitalize(),
                        color=colors[mode], linestyle=linestyles[mode],
                        linewidth=linewidths[mode], alpha=0.9)
        
        ax2.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax2.set_ylabel('OH Mass Fraction', fontsize=16, fontweight='bold')
        ax2.set_title('(b) OH Radical Profile', fontsize=17, fontweight='bold', pad=10)
        ax2.legend(loc='best', framealpha=0.95, fontsize=13)
        ax2.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
        ax2.ticklabel_format(style='scientific', axis='y', scilimits=(0,0))
        ax2.tick_params(labelsize=13, width=2, length=6)
    else:
        ax2.text(0.5, 0.5, 'OH species not found', ha='center', va='center',
                fontsize=16, transform=ax2.transAxes)
    
    for spine in ax2.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 3: H2 Profile ====================
    ax3 = axes[1, 0]
    if h2_idx is not None:
        for mode in modes:
            if results[mode]['traj'] is not None and len(results[mode]['traj']) > 0:
                times_ms = results[mode]['times'] * 1000
                h2_mass_frac = results[mode]['traj'][:, h2_idx]
                ax3.plot(times_ms, h2_mass_frac, label=mode.capitalize(),
                        color=colors[mode], linestyle=linestyles[mode],
                        linewidth=linewidths[mode], alpha=0.9)
        
        ax3.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax3.set_ylabel(r'H$_2$ Mass Fraction', fontsize=16, fontweight='bold')
        ax3.set_title('(c) Hydrogen Profile', fontsize=17, fontweight='bold', pad=10)
        ax3.legend(loc='best', framealpha=0.95, fontsize=13)
        ax3.grid(True, alpha=0.3, linestyle='--', linewidth=1.5)
        ax3.ticklabel_format(style='scientific', axis='y', scilimits=(0,0))
        ax3.tick_params(labelsize=13, width=2, length=6)
    else:
        ax3.text(0.5, 0.5, 'H2 species not found', ha='center', va='center',
                fontsize=16, transform=ax3.transAxes)
    
    for spine in ax3.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 4: Adaptive Solver Actions ====================
    ax4 = axes[1, 1]
    if 'adaptive' in results and results['adaptive']['used_solvers']:
        times_ms = results['adaptive']['times'] * 1000
        used_solvers = results['adaptive']['used_solvers']
        
        # Parse solver actions (handle fallback cases like 'cvode->qss')
        solver_timeline = []
        for action in used_solvers:
            if '->' in action:
                # Fallback occurred, use the second solver
                solver_timeline.append(action.split('->')[-1])
            else:
                solver_timeline.append(action)
        
        # Create numerical representation for plotting
        solver_map = {'cvode': 1, 'qss': 2}
        solver_numbers = [solver_map.get(s, 0) for s in solver_timeline]
        
        # Plot as step function
        ax4.step(times_ms, solver_numbers, where='post', linewidth=3.5, 
                color='#2E86AB', alpha=0.8)
        ax4.fill_between(times_ms, solver_numbers, step='post', alpha=0.3, color='#2E86AB')
        
        # Customize y-axis
        ax4.set_yticks([1, 2])
        ax4.set_yticklabels(['CVODE', 'QSS'], fontsize=14, fontweight='bold')
        ax4.set_ylim([0.5, 2.5])
        
        ax4.set_xlabel('Time (ms)', fontsize=16, fontweight='bold')
        ax4.set_ylabel('Active Solver', fontsize=16, fontweight='bold')
        ax4.set_title('(d) Adaptive Solver Selection', fontsize=17, fontweight='bold', pad=10)
        ax4.grid(True, alpha=0.3, linestyle='--', linewidth=1.5, axis='x')
        ax4.tick_params(labelsize=13, width=2, length=6)
        
        # Add transition count annotation
        transitions = sum(1 for i in range(len(solver_timeline)-1) 
                         if solver_timeline[i] != solver_timeline[i+1])
        ax4.text(0.98, 0.97, f'Transitions: {transitions}', 
                transform=ax4.transAxes, fontsize=13, fontweight='bold',
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    else:
        ax4.text(0.5, 0.5, 'Adaptive solver data not available', 
                ha='center', va='center', fontsize=16, transform=ax4.transAxes)
    
    for spine in ax4.spines.values():
        spine.set_linewidth(2)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"Figure saved to {save_path}")
    
    plt.show()


def plot_performance_comparison(results: Dict[str, Any], condition: Dict[str, Any],
                                save_path: str = None):
    """
    Create a 2x2 comparison plot showing CPU time, error, ignition delay, and solver usage.
    
    Parameters:
    -----------
    results : dict
        Dictionary containing results from different solver strategies
    condition : dict
        Simulation conditions
    save_path : str, optional
        Path to save the figure
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle('Solver Performance Comparison', fontsize=20, fontweight='bold', y=0.995)
    
    modes = ['cvode', 'qss', 'adaptive']  # Exclude reference from comparisons
    colors_comp = {'cvode': '#A23B72', 'qss': '#F18F01', 'adaptive': '#C73E1D'}
    
    # ==================== Plot 1: CPU Time Comparison ====================
    ax1 = axes[0, 0]
    cpu_times = [results[mode]['cpu_time'] for mode in modes]
    bars1 = ax1.bar(range(len(modes)), cpu_times, color=[colors_comp[m] for m in modes],
                    edgecolor='black', linewidth=2, alpha=0.85)
    
    # Add value labels on bars
    for i, (bar, time) in enumerate(zip(bars1, cpu_times)):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{time:.4f}s', ha='center', va='bottom', fontsize=13, fontweight='bold')
    
    ax1.set_xticks(range(len(modes)))
    ax1.set_xticklabels([m.upper() for m in modes], fontsize=14, fontweight='bold')
    ax1.set_ylabel('CPU Time (s)', fontsize=16, fontweight='bold')
    ax1.set_title('(a) Computational Cost', fontsize=17, fontweight='bold', pad=10)
    ax1.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=1.5)
    ax1.tick_params(labelsize=13, width=2, length=6)
    
    # Add speedup relative to reference
    if 'reference' in results:
        ref_time = results['reference']['cpu_time']
        speedups = [ref_time / results[mode]['cpu_time'] for mode in modes]
        ax1_twin = ax1.twinx()
        ax1_twin.plot(range(len(modes)), speedups, 'o-', color='#2E86AB', 
                     linewidth=3, markersize=12, label='Speedup vs Reference')
        ax1_twin.set_ylabel('Speedup Factor', fontsize=16, fontweight='bold', color='#2E86AB')
        ax1_twin.tick_params(axis='y', labelcolor='#2E86AB', labelsize=13, width=2, length=6)
        ax1_twin.legend(loc='upper right', fontsize=12, framealpha=0.9)
    
    for spine in ax1.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 2: Error Comparison ====================
    ax2 = axes[0, 1]
    
    # Collect errors
    temp_errors = []
    species_errors = []
    valid_modes = []
    
    for mode in modes:
        if results[mode]['error'] is not None:
            temp_err, species_err = results[mode]['error']
            temp_errors.append(temp_err * 100)  # Convert to percentage
            species_errors.append(species_err * 100)
            valid_modes.append(mode)
    
    if valid_modes:
        x = np.arange(len(valid_modes))
        width = 0.35
        
        bars2a = ax2.bar(x - width/2, temp_errors, width, label='Temperature Error',
                        color='#E63946', edgecolor='black', linewidth=2, alpha=0.85)
        bars2b = ax2.bar(x + width/2, species_errors, width, label='Species Error',
                        color='#457B9D', edgecolor='black', linewidth=2, alpha=0.85)
        
        # Add value labels
        for bars in [bars2a, bars2b]:
            for bar in bars:
                height = bar.get_height()
                ax2.text(bar.get_x() + bar.get_width()/2., height,
                        f'{height:.2f}%', ha='center', va='bottom', 
                        fontsize=11, fontweight='bold')
        
        ax2.set_xticks(x)
        ax2.set_xticklabels([m.upper() for m in valid_modes], fontsize=14, fontweight='bold')
        ax2.set_ylabel('Relative Error (%)', fontsize=16, fontweight='bold')
        ax2.set_title('(b) Accuracy vs Reference', fontsize=17, fontweight='bold', pad=10)
        ax2.legend(loc='best', fontsize=13, framealpha=0.95)
        ax2.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=1.5)
        ax2.set_yscale('log')
    else:
        ax2.text(0.5, 0.5, 'Error data not available', ha='center', va='center',
                fontsize=16, transform=ax2.transAxes)
    
    ax2.tick_params(labelsize=13, width=2, length=6)
    for spine in ax2.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 3: Ignition Delay Comparison ====================
    ax3 = axes[1, 0]
    
    ignition_delays = [results[mode]['ignition_delay'] * 1000 for mode in modes]  # Convert to ms
    bars3 = ax3.bar(range(len(modes)), ignition_delays, 
                    color=[colors_comp[m] for m in modes],
                    edgecolor='black', linewidth=2, alpha=0.85)
    
    # Add value labels
    for bar, delay in zip(bars3, ignition_delays):
        height = bar.get_height()
        ax3.text(bar.get_x() + bar.get_width()/2., height,
                f'{delay:.4f}ms', ha='center', va='bottom', fontsize=13, fontweight='bold')
    
    # Add reference line if available
    if 'reference' in results:
        ref_delay = results['reference']['ignition_delay'] * 1000
        ax3.axhline(y=ref_delay, color='#2E86AB', linestyle='--', linewidth=3,
                   label=f'Reference: {ref_delay:.4f}ms', alpha=0.8)
        ax3.legend(loc='best', fontsize=13, framealpha=0.95)
    
    ax3.set_xticks(range(len(modes)))
    ax3.set_xticklabels([m.upper() for m in modes], fontsize=14, fontweight='bold')
    ax3.set_ylabel('Ignition Delay (ms)', fontsize=16, fontweight='bold')
    ax3.set_title('(c) Ignition Timing', fontsize=17, fontweight='bold', pad=10)
    ax3.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=1.5)
    ax3.tick_params(labelsize=13, width=2, length=6)
    
    for spine in ax3.spines.values():
        spine.set_linewidth(2)
    
    # ==================== Plot 4: Adaptive Solver Usage ====================
    ax4 = axes[1, 1]
    
    if 'adaptive' in results and results['adaptive']['used_solvers']:
        used_solvers = results['adaptive']['used_solvers']
        
        # Parse solver usage (handle fallback cases)
        solver_usage = []
        for action in used_solvers:
            if '->' in action:
                # Count the final solver used after fallback
                solver_usage.append(action.split('->')[-1])
            else:
                solver_usage.append(action)
        
        # Count usage
        counter = Counter(solver_usage)
        total_steps = len(solver_usage)
        
        # Calculate percentages
        labels = []
        sizes = []
        colors_pie = []
        color_map = {'cvode': '#A23B72', 'qss': '#F18F01'}
        
        for solver in ['cvode', 'qss']:
            if solver in counter:
                labels.append(solver.upper())
                percentage = (counter[solver] / total_steps) * 100
                sizes.append(percentage)
                colors_pie.append(color_map[solver])
        
        # Create pie chart
        wedges, texts, autotexts = ax4.pie(sizes, labels=labels, colors=colors_pie,
                                            autopct='%1.1f%%', startangle=90,
                                            textprops={'fontsize': 15, 'fontweight': 'bold'},
                                            wedgeprops={'edgecolor': 'black', 'linewidth': 2})
        
        # Enhance percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontsize(16)
            autotext.set_fontweight('bold')
        
        ax4.set_title('(d) Adaptive Solver Distribution', fontsize=17, fontweight='bold', pad=10)
        
        # Add statistics box
        n_fallbacks = sum(1 for action in used_solvers if '->' in action)
        stats_text = f'Total Steps: {total_steps}\nFallbacks: {n_fallbacks}'
        ax4.text(0.02, 0.98, stats_text, transform=ax4.transAxes,
                fontsize=13, fontweight='bold', verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.9, edgecolor='black', linewidth=2))
    else:
        ax4.text(0.5, 0.5, 'Adaptive solver data not available',
                ha='center', va='center', fontsize=16, transform=ax4.transAxes)
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"Figure saved to {save_path}")
    
    plt.show()

if __name__ == "__main__":
    # Example usage: run four modes
    condition = {
        'temp': 900,
        'pressure': 60 * ct.one_atm,
        'Z': 0.055,
        'mechanism_option':'ndodecane',
        'dt': 1e-6,
        't_end': 1e-3
    }

    config = dict(SOLVER_CONFIG)

    # Prepare gas and initial state (shared)
    _gas, _state0 = prepare_case(condition)

    modes = ['reference', 'cvode', 'qss', 'adaptive']
    results = {}
    for mode in modes:
        print(f"Running {mode}...")
        # Each strategy gets its own gas clone to avoid internal state coupling
        gas = ct.Solution(_gas.source)
        gas.TPY = _gas.T, condition['pressure'], _gas.Y
        strat = build_strategy(mode, gas, condition['pressure'], config, _state0)
        if "reference" in results:
            reference_state = results['reference']['traj']
        else:
            reference_state = None
        out = integrate_loop(strat, _state0, condition['dt'], condition['t_end'], record=True, reference_state=reference_state)
        results[mode] = out


    plot_species_and_adaptive_actions(results, _gas, condition, 
                                      save_path='species_profiles.png')
    
    # Plot 2: Performance comparison
    plot_performance_comparison(results, condition, 
                               save_path='performance_comparison.png')
