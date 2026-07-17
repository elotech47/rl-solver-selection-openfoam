"""
Utility functions for QSS integrator.

This module provides helper functions for setting up and using the QSS integrator
with common combustion chemistry applications.
"""

import numpy as np
import cantera as ct
from pathlib import Path
from typing import Optional, Any, Dict, Tuple
import time
import SundialsPy as SP
from scipy.integrate import solve_ivp

# Try to import the compiled extension
try:
    from qss_integrator import QssIntegrator, PyQssOde
except ImportError:
    QssIntegrator = None
    PyQssOde = None


def combustion_rhs(
    t: float, y: np.ndarray, gas: ct.Solution, pressure: float
) -> np.ndarray:
    """Right-hand side of the combustion ODE system.

    Args:
        t: Current time
        y: Current state vector [T, Y1, Y2, ...]
        gas: Cantera gas object
        pressure: Constant pressure

    Returns:
        dydt: Time derivatives [dT/dt, dY1/dt, dY2/dt, ...]
    """
    # Extract temperature and mass fractions
    T = y[0]
    Y = y[1:]

    # Update the gas state
    gas.TPY = T, pressure, Y

    # Get thermodynamic properties
    rho = gas.density_mass
    wdot = gas.net_production_rates
    cp = gas.cp_mass
    h = gas.partial_molar_enthalpies

    # Calculate temperature derivative (energy equation)
    dTdt = -(np.dot(h, wdot) / (rho * cp))

    # Calculate species derivatives (mass conservation)
    dYdt = wdot * gas.molecular_weights / rho

    # Combine into full derivative vector
    return np.hstack([dTdt, dYdt])


class CanteraQSSODE:
    """QSS ODE implementation for Cantera combustion systems."""

    def __init__(self, gas: ct.Solution, pressure: float):
        """Initialize the QSS ODE for a Cantera gas object.

        Args:
            gas: Cantera Solution object
            pressure: Constant pressure [Pa]
        """
        self.gas = gas
        self.pressure = pressure
        self.n_species = self.gas.n_species
        # caches for corrector
        self._T_cache = None
        self._rho_cache = None
        self._cp_cache = None
        self._hform_cache = None

    def __call__(self, t: float, y: list, corrector: bool = False) -> Tuple[list, list]:
        """Evaluate the ODE splitting for QSS method.

        Args:
            t: Current time
            y: Current state vector [T, Y1, Y2, ...]
            corrector: Whether this is a corrector iteration

        Returns:
            (q, d): Production and destruction rate vectors
        """
        # unpack state
        T_in = max(y[0], 300.0)
        Y = np.maximum(np.array(y[1:], dtype=float), 0.0)
        s = Y.sum()
        if s > 1e-12:
            Y /= s

        if not corrector:
            # predictor: set state and compute thermo
            self.gas.TPY = T_in, self.pressure, Y
            rho = self.gas.density
            cp = self.gas.cp_mass
            h_form = self.gas.standard_enthalpies_RT * ct.gas_constant * self.gas.T
            # cache for the corrector
            self._T_cache = self.gas.T
            self._rho_cache = rho
            self._cp_cache = cp
            self._hform_cache = h_form
        else:
            # corrector: freeze T/thermo like C++
            # (still update composition to get updated rates with the new Y)
            T_frozen = self._T_cache if self._T_cache is not None else T_in
            self.gas.TPY = T_frozen, self.pressure, Y
            rho = self._rho_cache if self._rho_cache is not None else self.gas.density
            cp = self._cp_cache if self._cp_cache is not None else self.gas.cp_mass
            h_form = (
                self._hform_cache
                if self._hform_cache is not None
                else self.gas.standard_enthalpies_RT * ct.gas_constant * T_frozen
            )

        # rates (ensure nonnegative split)
        wQ = np.maximum(self.gas.creation_rates, 0.0)  # kmol/m^3/s
        wD = np.maximum(self.gas.destruction_rates, 0.0)  # kmol/m^3/s
        net = wQ - wD
        qdot = -np.dot(
            net, h_form
        )  # J/m^3/s  (exothermic release is negative enthalpy change)

        # temperature parts: chemistry heat into q-part; put losses (if any) into d-part
        dTdt_q = qdot / (rho * cp)  # + split energy if you have it
        dTdt_d = 0.0  # add heat-loss/(rho*cp) here if modeling losses

        # species parts (mass-fraction rates)
        W = self.gas.molecular_weights  # kg/kmol
        dYdt_q = wQ * W / rho  # + split species if you have them
        dYdt_d = wD * W / rho

        q = np.concatenate(([dTdt_q], dYdt_q))
        d = np.concatenate(([dTdt_d], dYdt_d))
        return q.tolist(), d.tolist()


# Global dictionary to store references and prevent garbage collection
_qss_refs = {}


def create_qss_solver(
    gas: ct.Solution, pressure: float, config: Dict[str, Any]
) -> QssIntegrator:
    """Create a QSS solver for a Cantera combustion system.

    Args:
        gas: Cantera Solution object
        pressure: Constant pressure [Pa]
        config: Solver configuration dictionary

    Returns:
        Initialized QSS integrator
    """
    if QssIntegrator is None or PyQssOde is None:
        raise ImportError(
            "QSS C++ extension not available. Please build the package first."
        )

    chem = CanteraQSSODE(gas, pressure)
    integrator = QssIntegrator()
    ode_qss = PyQssOde(chem)

    integrator.setOde(ode_qss)
    integrator.initialize(chem.n_species + 1)

    # Set configuration parameters
    integrator.epsmin = config.get("epsmin", 1e-2)
    integrator.epsmax = config.get("epsmax", 20.0)
    integrator.dtmin = config.get("dtmin", 1e-15)
    integrator.dtmax = config.get("dtmax", 1e-6)
    integrator.itermax = config.get("itermax", 2)
    integrator.abstol = config.get("abstol", 1e-8)
    integrator.stabilityCheck = config.get("stabilityCheck", True)

    # Store references in global dictionary to prevent garbage collection
    integrator_id = id(integrator)
    _qss_refs[integrator_id] = (chem, ode_qss)

    return integrator

class ScipyCVodeSolver:
    """Scipy-based CVODE-compatible solver using scipy's ODE integrator.
    
    This class provides the same interface as SP.cvode.CVodeSolver but uses
    scipy's ODE integrator under the hood.
    """
    
    def __init__(self, system_size: int, rhs_fn: callable, iter_type: Any = None, 
                 mxsteps: int = 1000, verbose: int = -1):
        """Initialize the scipy-based CVODE solver.
        
        Args:
            system_size: Size of the ODE system
            rhs_fn: Right-hand side function f(t, y) -> dydt
            iter_type: Ignored (for compatibility with CVodeSolver interface)
            mxsteps: Maximum number of steps
            verbose: Verbosity level (ignored)
        """
        self.system_size = system_size
        self.rhs_fn = rhs_fn
        self.mxsteps = mxsteps
        self._current_state = None
        self._current_time = 0.0
        self._rtol = None
        self._atol = None
        
    def initialize(self, y: np.ndarray, t: float, rtol: float, atol: np.ndarray):
        """Initialize the solver with initial conditions.
        
        Args:
            y: Initial state vector
            t: Initial time
            rtol: Relative tolerance
            atol: Absolute tolerance (scalar or array)
        """
        self._current_state = np.array(y, copy=True)
        self._current_time = float(t)
        self._rtol = float(rtol)
        if np.isscalar(atol):
            self._atol = float(atol)
        else:
            self._atol = np.asarray(atol)
    
    def set_state(self, state: np.ndarray, t: float):
        """Set the current state and time.
        
        Args:
            state: Current state vector
            t: Current time (typically 0.0 when called from step)
        """
        self._current_state = np.array(state, copy=True)
        self._current_time = float(t)
    
    def solve_to(self, t_end: float) -> Tuple[np.ndarray, bool, int]:
        """Integrate from current time to t_end.
        
        Args:
            t_end: Target time
            
        Returns:
            (new_state, success, error_code)
            - new_state: State at t_end
            - success: True if integration succeeded
            - error_code: 0 if success, 1 if failure
        """
        if self._current_state is None:
            raise RuntimeError("Solver not initialized. Call initialize() first.")
        
        if self._rtol is None or self._atol is None:
            raise RuntimeError("Solver not initialized with tolerances.")
        
        try:
            # Use scipy's solve_ivp with BDF method (similar to CVODE BDF)
            result = solve_ivp(
                fun=lambda t, y: self.rhs_fn(t, y),
                t_span=(self._current_time, t_end),
                y0=self._current_state,
                method='BDF',  # BDF method similar to CVODE
                rtol=self._rtol,
                atol=self._atol,
                max_step=np.inf,  # Let scipy choose step size
                dense_output=False,
                first_step=None,
                max_nfev=self.mxsteps,  # large cap; mxsteps controls actual step budget
            )
            
            if result.success:
                # Update internal state
                self._current_state = result.y[:, -1]
                self._current_time = result.t[-1]
                return self._current_state.copy(), True, 0
            else:
                # Integration failed
                return self._current_state.copy(), False, 1
                
        except Exception as e:
            # Any exception is treated as failure
            return self._current_state.copy(), False, 1


def create_cvode_solver(method: str, config: Dict[str, Any], gas: ct.Solution, y: np.ndarray, t: float, pressure: float, mxsteps: int = 1000) -> Any:
    """Create a SUNDIALS solver.
    
    Args:
        method: Solver method ('cvode_bdf', 'cvode_adams', 'arkode_erk')
        system_size: Size of the ODE system
        config: Solver configuration dictionary
        gas: Cantera gas object
        pressure: Constant pressure
        mxsteps: Maximum number of steps
    Returns:
        solver: Initialized SUNDIALS solver
    """
    system_size = 1 + gas.n_species
    atol = config.get("atol", 1e-8)
    rtol = config.get("rtol", 1e-8)
    # Create absolute tolerance array
    if np.isscalar(atol):
        abs_tol = np.ones(system_size) * atol
    else:
        abs_tol = np.asarray(atol)
        if len(abs_tol) == 1:
            abs_tol = np.ones(system_size) * abs_tol[0]
        
    if method == 'cvode':
        #print(f"Creating cvode_bdf solver")
        solver = SP.cvode.CVodeSolver(
            system_size=system_size,
            rhs_fn=lambda t, y: combustion_rhs(t, y, gas, pressure),
            iter_type=SP.cvode.IterationType.NEWTON,
            mxsteps=mxsteps,
            verbose=-1
        )
        solver.initialize(y, t, rtol, abs_tol)

        return solver
    elif method == 'cvode_scipy':
        #print(f"Creating cvode_scipy solver")
        # Create scipy-based CVODE-compatible solver
        solver = ScipyCVodeSolver(
            system_size=system_size,
            rhs_fn=lambda t, y: combustion_rhs(t, y, gas, pressure),
            iter_type=None,  # Not used for scipy
            mxsteps=mxsteps,
            verbose=-1
        )
        solver.initialize(y, t, rtol, abs_tol)
        return solver
    else:
        raise ValueError(f"Unknown SUNDIALS method: {method}")
    

def create_solver(method: str, config: Dict[str, Any], gas: ct.Solution, y: np.ndarray, t: float, 
                 pressure: float = ct.one_atm, mxsteps: int = 1000) -> Any:
    """Create the appropriate solver based on method.
    
    Args:
        method: Solver method string
        config: Solver configuration dictionary
        gas: Cantera gas object
        y: Current state
        t: Current time
        pressure: Constant pressure [Pa]
        mxsteps: Maximum number of steps
    Returns:
        solver: Initialized solver
    """
    system_size = 1 + gas.n_species
    
    if method.startswith('cvode'):
        return create_cvode_solver(method, config, gas, y, t, pressure, mxsteps)
    elif method.startswith('qss'):
        return create_qss_solver(gas, pressure, config)
    else:
        raise ValueError(f"Unknown solver method: {method}")
    
    
MECHANISM_CONFIGS = {
    'hydrogen': {
        # Cantera built-in; not shipped as package data.
        'mechanism': 'h2o2.yaml',
        'package_resource': False,
        'fuel': 'h2:1.0',
        'oxidizer': 'n2:3.76, o2:1.0',
        'key_species': ['OH', 'H2O', 'O2', 'H2', 'H2O2', 'O', 'H', 'N2'],
    },
    'methane': {
        'mechanism': 'ch4_53species.yaml',
        'package_resource': True,
        'fuel': 'ch4:1.0',
        'oxidizer': 'n2:3.76, o2:1.0',
        'key_species': ['OH', 'H2O', 'O2', 'H2', 'H2O2', 'O', 'H', 'N2'],
    },
    'ndodecane': {
        'mechanism': 'n-dodecane.yaml',
        'package_resource': True,
        'fuel': 'nc12h26:1.0',
        'oxidizer': 'n2:3.76, o2:1.0',
        'key_species': ['OH', 'H2O', 'O2', 'H2', 'H2O2', 'O', 'H', 'N2'],
    },
    'jetA': {
        'mechanism': 'mech.yaml',
        'package_resource': True,
        'fuel': 'POSF10325:1.0',
        'oxidizer': 'N2:3.76, O2:1.0',
        'key_species': ['OH', 'H2O', 'O2', 'H2', 'H2O2', 'O', 'H', 'N2'],
    },
}


def package_mechanisms_dir() -> Path:
    """Directory of Cantera YAML mechanisms shipped with this package."""
    return Path(__file__).resolve().parent / "data" / "mechanisms"


def resolve_mechanism_path(mechanism_key_or_path: str) -> Path:
    """
    Resolve a named mechanism key or filesystem path to a Cantera YAML path.

    Named keys that ship with the package (``ndodecane``, ``methane``, ``jetA``)
    resolve under ``data/mechanisms/``. ``hydrogen`` uses Cantera's built-in
    ``h2o2.yaml`` (returned as a bare name Path for ``ct.Solution``).
    """
    key = str(mechanism_key_or_path).strip()
    if key in MECHANISM_CONFIGS:
        cfg = MECHANISM_CONFIGS[key]
        fname = cfg["mechanism"]
        if cfg.get("package_resource", False):
            path = package_mechanisms_dir() / fname
            if not path.is_file():
                raise FileNotFoundError(
                    f"Packaged mechanism missing: {path}"
                )
            return path
        return Path(fname)  # Cantera built-in name
    path = Path(key).expanduser()
    if not path.is_absolute():
        # Prefer CWD, then package mechanisms dir.
        cwd_candidate = Path.cwd() / path
        pkg_candidate = package_mechanisms_dir() / path.name
        if cwd_candidate.is_file():
            return cwd_candidate.resolve()
        if pkg_candidate.is_file():
            return pkg_candidate.resolve()
        return cwd_candidate.resolve()
    return path.resolve()