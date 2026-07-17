import numpy as np
import torch
import torch.nn as nn
import cantera as ct
from torch.distributions import Categorical
import math
from typing import Tuple, List

# Ensure checkpoints pickled with flat ``ppo_agent`` resolve under this package.
from . import _compat  # noqa: F401
from .ppo_agent import PPOAgent, PPOConfig


class RLSolverSelector:
    """Lightweight RL policy inference for CFD integration"""
    
    def __init__(self, model_path, mechanism_file, device='cpu', network_config={"hidden_dims": [256, 256, 128], "activation": "tanh"}, key_species=['O','H','OH','H2O','O2','H2','H2O2','N2'],
                 use_prev_state=True, confidence_threshold=0.6, use_gradient_only=False):
        """
        Initialize the RL solver selector
        
        Args:
            model_path: Path to saved PyTorch model (.pt file)
            mechanism_file: Path to Cantera mechanism file
            solver_configs: List of solver configurations (optional, for name mapping)
            network_config: Dictionary containing network configuration
            device: 'cpu' or 'cuda'
        """
        self.device = device
        self.mechanism_file = mechanism_file
        self.confidence_threshold = confidence_threshold
        # Load Cantera gas object
        self.gas = ct.Solution(mechanism_file)
        
        self.network_config = network_config
        self.agent = self._load_agent(model_path)
        
        # Key species for observation (same as training)
        self.key_species = key_species
        self.key_species_indices = np.array([self.gas.species_index(spec) for spec in self.key_species])    
        print(f"Key species indices: {self.key_species_indices}")

        self.use_prev_state = use_prev_state
        self.use_gradient_only = use_gradient_only
        self.x = None
        self.reset()
        
    def reset(self):
        """Reset the RL agent."""
        if self.use_prev_state:
            self.prev_state = None
            self.prev_state_batch = None
    
    def _load_agent(self, checkpoint_path: str):
        """Load trained RL agent."""
        
        checkpoint = torch.load(checkpoint_path, map_location=self.device, weights_only=False)
        
        # Get network config from checkpoint or use defaults
        ppo_config = checkpoint.get('config', PPOConfig())
        
        # Determine dimensions (from checkpoint)
        if 'network_state_dict' in checkpoint:
            network_state = checkpoint['network_state_dict']
        else:
            network_state = checkpoint
        obs_dim = network_state['feature_extractor.0.weight'].shape[1]
        action_dim = network_state['actor.weight'].shape[0]
    
        # Create agent
        agent = PPOAgent(
            obs_dim=obs_dim,
            action_dim=action_dim,
            config=ppo_config,
            network_config=self.network_config
        )
        
        # Load weights
        agent.network.load_state_dict(network_state)
        agent.network.eval()  # Set to evaluation mode

        # Restore obs_rms statistics so inference normalization matches training.
        # Without this, unnormalized observations are fed to a network that was
        # trained on normalized inputs, causing degenerate (e.g. always-QSS) behaviour.
        if 'obs_rms' in checkpoint:
            agent.obs_rms.mean  = checkpoint['obs_rms']['mean']
            agent.obs_rms.var   = checkpoint['obs_rms']['var']
            agent.obs_rms.count = checkpoint['obs_rms']['count']
        
        print(f"✅ Loaded RL agent from {checkpoint_path}")
        print(f"   Obs dim: {obs_dim}, Action dim: {action_dim}")
        
        return agent
    
    def _select_action(self, obs: np.ndarray, deterministic: bool = True) -> Tuple[int, float, float]:
        """
        Select action using trained agent.
        
        Args:
            obs: Observation array
            deterministic: If True, use argmax; if False, sample from distribution
        
        Returns:
            action: Selected action (0=CVODE, 1=QSS)
            confidence: Confidence/probability of selected action
            cpu_time: Time taken for inference (seconds)
        """
        import time
        
        start = time.time()
        
        with torch.no_grad():
            # Apply the same obs_rms normalization used during training.
            norm_obs = self.agent._normalize_observation(obs)
            obs_tensor = torch.from_numpy(norm_obs).float().unsqueeze(0).to(self.device)
            #print(f"Obs tensor: {obs_tensor}")
            if deterministic:
                action, _, _ = self.agent.network.get_action(obs_tensor, deterministic=True)
                action = action.item()
                
                # Get confidence by computing softmax probabilities
                logits, _ = self.agent.network(obs_tensor)
                probs = torch.softmax(logits, dim=1)
                confidence = probs[0, action].item()
            else:
                action, _, _ = self.agent.network.get_action(obs_tensor, deterministic=False)
                action = action.item()
                
                # Get confidence from the sampled action
                logits, _ = self.agent.network(obs_tensor)
                dist = Categorical(logits=logits)
                confidence = torch.exp(dist.log_prob(torch.tensor([action]))).item()
        #print(f"Action: {action} - Confidence: {confidence}")
        cpu_time = time.time() - start
        
        return action, confidence, cpu_time

    def select_action_detailed(
        self, obs: np.ndarray, deterministic: bool = True
    ) -> Tuple[int, float, np.ndarray, float]:
        """
        Single forward pass: policy action, confidence, class probabilities, cpu_time.

        Uses the same obs_rms normalization as _select_action. Probabilities match
        the logits softmax (argmax equals deterministic action).
        """
        import time

        start = time.time()
        with torch.no_grad():
            norm_obs = self.agent._normalize_observation(obs)
            obs_tensor = torch.from_numpy(norm_obs).float().unsqueeze(0).to(self.device)
            logits, _ = self.agent.network(obs_tensor)
            probs_t = torch.softmax(logits, dim=1)[0]
            probs = probs_t.cpu().numpy()
            if deterministic:
                action = int(torch.argmax(logits, dim=1).item())
                confidence = float(probs_t[action].item())
            else:
                dist = Categorical(logits=logits)
                a = dist.sample()
                action = int(a.item())
                confidence = float(torch.exp(dist.log_prob(a)).item())
        cpu_time = time.time() - start
        return action, confidence, probs.astype(np.float32), cpu_time
    
    def _select_action_batch(self, obs_batch: np.ndarray, deterministic: bool = True) -> Tuple[List[int], List[float], float]:
        """
        Select actions for a batch of observations using trained agent.
        
        Args:
            obs_batch: Batch of observation arrays, shape (N, obs_dim)
            deterministic: If True, use argmax; if False, sample from distribution
        
        Returns:
            actions: List of selected actions
            confidences: List of confidence/probability values
            cpu_time: Total time taken for batch inference (seconds)
        """
        import time
        
        start = time.time()
        
        with torch.no_grad():
            # Apply the same obs_rms normalization used during training.
            norm_batch = np.stack([self.agent._normalize_observation(o) for o in obs_batch])
            obs_tensor = torch.from_numpy(norm_batch).float().to(self.device)
            
            if deterministic:
                # Get actions deterministically
                actions = []
                confidences = []
                
                for i in range(obs_tensor.shape[0]):
                    single_obs = obs_tensor[i:i+1]  # Keep batch dimension
                    action, _, _ = self.agent.network.get_action(single_obs, deterministic=True)
                    action = action.item()
                    actions.append(action)
                    
                    # Get confidence
                    logits, _ = self.agent.network(single_obs)
                    probs = torch.softmax(logits, dim=1)
                    confidence = probs[0, action].item()
                    confidences.append(confidence)
            else:
                # Sample actions
                actions = []
                confidences = []
                
                for i in range(obs_tensor.shape[0]):
                    single_obs = obs_tensor[i:i+1]  # Keep batch dimension
                    action, _, _ = self.agent.network.get_action(single_obs, deterministic=False)
                    action = action.item()
                    actions.append(action)
                    
                    # Get confidence from sampled action
                    logits, _ = self.agent.network(single_obs)
                    dist = Categorical(logits=logits)
                    confidence = torch.exp(dist.log_prob(torch.tensor([action]))).item()
                    confidences.append(confidence)
        
        cpu_time = time.time() - start
        
        return actions, confidences, cpu_time
    
    def apply_hysteresis(self, actions: List[int], confidences: List[float], 
                        confidence_threshold: float = 0.8, default_action: int = 0) -> List[int]:
        """
        Apply hysteresis to action predictions to reduce noise and improve stability.
        
        Args:
            actions: List of predicted actions
            confidences: List of confidence values corresponding to actions
            confidence_threshold: Minimum confidence required to keep predicted action
            default_action: Action to use when confidence is below threshold
        
        Returns:
            List of actions with hysteresis applied
        """
        if not actions or not confidences:
            return actions
        
        # Convert to numpy arrays for easier manipulation
        actions = np.array(actions)
        confidences = np.array(confidences)
        filtered_actions = actions.copy()
        
        # Step 1: Apply confidence threshold
        low_confidence_mask = confidences < confidence_threshold
        filtered_actions[low_confidence_mask] = default_action
        
        # Step 2: Handle sandwiched action 0s (action 0 between two action 1s)
        # Also handle neighbors of sandwiched action 0s
        for i in range(1, len(filtered_actions) - 1):
            # Check if current action is 0 and neighbors are 1
            if (filtered_actions[i] == 0 and 
                filtered_actions[i-1] == 1 and 
                filtered_actions[i+1] == 1):
                # Set the sandwiched 0 and its neighbors to 0
                filtered_actions[i-1] = 0
                filtered_actions[i] = 0
                filtered_actions[i+1] = 0
                
                
        # Step 3: Handle sandwiched block(s) of action 1s between two action 0s
        i = 1
        while i < len(filtered_actions) - 1:
            # Look for region: 0, [one or more 1s], 0
            if (filtered_actions[i-1] == 0):
                j = i
                while j < len(filtered_actions) - 1 and filtered_actions[j] == 1:
                    j += 1
                if (j > i) and (filtered_actions[j] == 0):
                    # Set the block and both neighbors to default_action
                    filtered_actions[i-1:j+1] = default_action
                    i = j  # jump to end of the block
                else:
                    i += 1
            else:
                i += 1

        return filtered_actions.tolist()
    
    def _get_observation(self, temperature, pressure, species_fractions, use_old_observation=False):
        """
        Convert temperature and species to normalized observation
        
        Args:
            temperature: Temperature in K
            species_fractions: Mass fractions array (same order as gas.species_names)
            pressure: Pressure in Pa
        
        Returns:
            Normalized observation tensor
        """
        if use_old_observation:
            Y_key = np.array([species_fractions[idx] for idx in self.key_species_indices])
            log_T = [np.log10(temperature)]
            Y_key_trans = np.log10(np.maximum(np.abs(Y_key), 1e-20))
            log_P = [np.log10(pressure)]

            return np.concatenate([log_T, Y_key_trans, log_P]).astype(np.float32)
        else:
            T = (temperature - 300.0) / 2000.0
            P = np.log10(pressure / ct.one_atm)
            Y_key = np.array([species_fractions[idx] for idx in self.key_species_indices])
            Y_key_trans = np.log10(np.maximum(np.abs(Y_key), 1e-20))

            if self.use_gradient_only:
                print(f"USING GRADIENT ONLY")
                if self.prev_state is None:
                    self.prev_state = np.array([temperature, species_fractions])
                prev_Y_key = np.array([self.prev_state[idx] for idx in self.key_species_indices])
                prev_Y_key_trans = np.log10(np.maximum(np.abs(prev_Y_key), 1e-20))
                dTdt = (np.log10(temperature) - np.log10(self.prev_state[0]))
                dYdt = (Y_key_trans - prev_Y_key_trans)
                obs = np.concatenate([[dTdt], dYdt, [P]]).astype(np.float32)
                self.prev_state = np.array([temperature, species_fractions])
                return obs
            if self.use_prev_state:
                print(f"USING PREV STATE")
                if self.prev_state is None:
                    self.prev_state = np.array([temperature, species_fractions])
                prev_Y_key = np.array([self.prev_state[idx] for idx in self.key_species_indices])
                prev_Y_key_trans = np.log10(np.maximum(np.abs(prev_Y_key), 1e-20))
                dTdt = (np.log10(temperature) - np.log10(self.prev_state[0]))
                dYdt = (Y_key_trans - prev_Y_key_trans)
                obs = np.concatenate([[T], Y_key_trans, [P], [dTdt], dYdt]).astype(np.float32)
                self.prev_state = np.array([temperature, species_fractions])
                return obs
            else:
                print(f"USING LEGACY OBSERVATION")
                obs = np.concatenate([[T], Y_key_trans, [P]]).astype(np.float32)
                return obs
    
    def _get_observation_batch(self, temperatures, species_fractions_batch, pressure, use_old_observation=False, x=None):
        """
        Vectorized observation builder for a batch of grid points.
        
        Args:
            temperatures: 1D array-like of temperatures (K), shape (N,)
            pressure: Pressure in Pa
            species_fractions_batch: 2D array of mass fractions, shape (N, num_species)
            x: 1D array-like of spatial locations of current grid, shape (N,)
        Returns:
            obs_batch: 2D numpy array, shape (N, obs_dim)
        """
        num_points = temperatures.shape[0]
        temperatures = np.asarray(temperatures, dtype=np.float32)
        pressure = np.asarray([pressure] * num_points, dtype=np.float32)
        species_fractions_batch = np.asarray(species_fractions_batch, dtype=np.float32)
        if x is not None:
            x = np.asarray(x)
        else:
            x = None

        if use_old_observation:
            log_T = np.log10(temperatures).reshape(num_points, 1)
            log_P = np.log10(pressure).reshape(num_points, 1)
            Y_key_trans = np.log10(np.maximum(np.abs(species_fractions_batch[:, self.key_species_indices]), 1e-20))
            obs_batch = np.hstack([log_T, Y_key_trans, log_P]).astype(np.float32)
        else:
            T = (temperatures - 300.0) / 2000.0
            T = T.reshape(num_points, 1)
            P = np.log10(pressure / ct.one_atm)
            P = P.reshape(num_points, 1)
            Y_key_trans = np.log10(np.maximum(np.abs(species_fractions_batch[:, self.key_species_indices]), 1e-20))
            Y_key_trans = Y_key_trans.reshape(num_points, len(self.key_species_indices))
            
            if self.use_prev_state:
                # Detect if x grid changed between steps
                grid_changed = False
                old_indices = None
                if self.prev_state_batch is not None and self.x is not None and x is not None:
                    if len(self.x) != len(x) or not np.allclose(self.x, x):
                        # For each x in the current grid, find its closest index in the previous grid
                        old_indices = np.array([np.argmin(np.abs(self.x - xval)) for xval in x])
                        grid_changed = True

                if self.prev_state_batch is None or (x is not None and (self.x is None or grid_changed)):
                    # On very first call, or first after grid has changed, set prev states accordingly
                    self.prev_state_batch = (temperatures.copy(), species_fractions_batch.copy())
                    if x is not None:
                        self.x = x.copy()
                    # set dTdt, dYdt to zeros (no previous info available)
                    dTdt = np.zeros((num_points,1), dtype=np.float32)
                    dYdt = np.zeros((num_points, len(self.key_species_indices)), dtype=np.float32)
                else:
                    prev_temperatures, prev_species_fractions = self.prev_state_batch
                    # Properly align previous state to current x using indices if grids changed
                    if grid_changed and old_indices is not None:
                        prev_temperatures = prev_temperatures[old_indices]
                        prev_species_fractions = prev_species_fractions[old_indices]
                    prev_Y_key_trans = np.log10(np.maximum(np.abs(prev_species_fractions[:, self.key_species_indices]), 1e-20))
                    dTdt = (np.log10(temperatures) - np.log10(prev_temperatures)).reshape(num_points, 1)
                    dYdt = (Y_key_trans - prev_Y_key_trans)
                    # Update prev states
                    self.prev_state_batch = (temperatures.copy(), species_fractions_batch.copy())
                    if x is not None:
                        self.x = x.copy()
                obs_batch = np.hstack([T, Y_key_trans, P, dTdt, dYdt]).astype(np.float32)
            else:
                obs_batch = np.hstack([T, Y_key_trans, P]).astype(np.float32)

        if self.x is None and x is not None:
            self.x = x.copy()
        
        return obs_batch
    
    @torch.no_grad()
    def select_solver(self, temperature, species_fractions, pressure, deterministic=True, use_old_observation=False):
        """
        Select solver based on current state
        
        Args:
            temperature: Temperature in K
            species_fractions: Mass fractions array
            pressure: Pressure in Pa
            deterministic: If True, use argmax; if False, sample from distribution
        
        Returns:
            action (int): Solver index
            confidence (float): Confidence/probability of selected action
            cpu_time (float): Time taken for inference (seconds)
        """
        # Get observation
        obs = self._get_observation(temperature, pressure, species_fractions, use_old_observation)
        
        # Use _select_action for consistent behavior
        action, confidence, cpu_time = self._select_action(obs, deterministic)
        # print(f"Action: {action}")
        # print(f"Confidence: {confidence}")
        # print(f"CPU time: {cpu_time}")
        return action, confidence, cpu_time
    
    @torch.no_grad()
    def select_solver_batch(self, temperatures, species_fractions_batch, pressure, deterministic=True, use_old_observation=False, x=None):
        """
        Vectorized solver selection for multiple grid points.
        
        Args:
            temperatures: 1D array of temperatures (K) with shape (N,)
            species_fractions_batch: 2D array of mass fractions with shape (N, num_species)
            pressure: Pressure in Pa
            deterministic: If True, use argmax; otherwise sample per point
        Returns:
            actions: list[int] of length N
            confidences: list[float] of length N
            cpu_time: Total time taken for batch inference (seconds)
        """
        # Build and normalize observations in batch
        obs_batch = self._get_observation_batch(temperatures, species_fractions_batch, pressure, use_old_observation, x)
        
        # Use _select_action_batch for consistent behavior
        actions, confidences, cpu_time = self._select_action_batch(obs_batch, deterministic)
        # print(f"Actions: {actions}")
        # print(f"Confidences: {confidences}")
        # print(f"CPU time: {cpu_time}")
        return actions, confidences, cpu_time
    
    def select_solver_batch_with_hysteresis(self, temperatures, species_fractions_batch, pressure, 
                                          deterministic=True, use_old_observation=False,
                                          confidence_threshold=0.5, default_action=0):
        """
        Vectorized solver selection with hysteresis applied for multiple grid points.
        
        Args:
            temperatures: 1D array of temperatures (K) with shape (N,)
            species_fractions_batch: 2D array of mass fractions with shape (N, num_species)
            pressure: Pressure in Pa
            deterministic: If True, use argmax; otherwise sample per point
            confidence_threshold: Minimum confidence required to keep predicted action
            default_action: Action to use when confidence is below threshold
        
        Returns:
            actions: list[int] of length N (with hysteresis applied)
            confidences: list[float] of length N
            cpu_time: Total time taken for batch inference (seconds)
        """
        # Get raw predictions
        raw_actions, confidences, cpu_time = self.select_solver_batch(
            temperatures, species_fractions_batch, pressure, deterministic, use_old_observation
        )
        
        # Apply hysteresis
        filtered_actions = self.apply_hysteresis(raw_actions, confidences, confidence_threshold, default_action)
        
        return filtered_actions, confidences, cpu_time
    
    def __call__(self, temperature, species_fractions, pressure, deterministic=True, use_old_observation=False):
        """
        Convenient callable interface
        
        Args:
            temperature: Temperature in K
            species_fractions: Mass fractions array
            pressure: Pressure in Pa
            deterministic: Whether to use deterministic action selection
        
        Returns:
            action (int): Selected solver index
        """
        action, _, _ = self.select_solver(temperature, species_fractions, pressure, deterministic, use_old_observation)
        return action
    
