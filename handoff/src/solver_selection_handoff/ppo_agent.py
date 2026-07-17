
"""
PPO Agent - Core Algorithm Implementation

Pure algorithm implementation with no training logic.
Designed to be reusable and testable.
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class PPOConfig:
    """PPO hyperparameters configuration."""
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    max_grad_norm: float = 0.5
    ppo_epochs: int = 4  # Reduced from 10 to prevent overfitting
    minibatch_size: int = 64
    device: str = 'cpu'


class ActorCriticNetwork(nn.Module):
    """
    Actor-Critic network for discrete action space.
    
    Architecture:
    - Shared feature extraction layers
    - Separate heads for policy (actor) and value (critic)
    """
    
    def __init__(
        self, 
        obs_dim: int, 
        action_dim: int,
        hidden_dims: List[int] = [128, 128],
        activation: str = 'tanh'
    ):
        super().__init__()
        
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        
        # Activation function
        if activation == 'tanh':
            act_fn = nn.Tanh
        elif activation == 'relu':
            act_fn = nn.ReLU
        else:
            raise ValueError(f"Unknown activation: {activation}")
        
        # Shared feature extractor
        layers = []
        prev_dim = obs_dim
        for hidden_dim in hidden_dims:
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                act_fn(),
            ])
            prev_dim = hidden_dim
        
        self.feature_extractor = nn.Sequential(*layers)
        
        # Actor head (policy)
        self.actor = nn.Linear(prev_dim, action_dim)
        
        # Critic head (value function)
        self.critic = nn.Linear(prev_dim, 1)
        
        # Initialize weights
        self._init_weights()
    
    def _init_weights(self):
        """Orthogonal initialization for better training."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.orthogonal_(module.weight, gain=np.sqrt(2))
                nn.init.constant_(module.bias, 0.0)
        
        # Smaller init for policy head (helps with exploration)
        nn.init.orthogonal_(self.actor.weight, gain=0.01)
        nn.init.constant_(self.actor.bias, 0.0)
    
    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            obs: Observation tensor [batch_size, obs_dim]
        
        Returns:
            action_logits: [batch_size, action_dim]
            value: [batch_size, 1]
        """
        features = self.feature_extractor(obs)
        action_logits = self.actor(features)
        value = self.critic(features)
        return action_logits, value
    
    def get_action(self, obs: torch.Tensor, deterministic: bool = False) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Sample action from policy.
        
        Args:
            obs: Observation [batch_size, obs_dim] or [obs_dim]
            deterministic: If True, take argmax action
        
        Returns:
            action: [batch_size] or scalar
            log_prob: [batch_size] or scalar
            value: [batch_size] or scalar
        """
        action_logits, value = self.forward(obs)
        
        # Get action distribution
        dist = torch.distributions.Categorical(logits=action_logits)
        
        if deterministic:
            action = torch.argmax(action_logits, dim=-1)
        else:
            action = dist.sample()
        
        log_prob = dist.log_prob(action)
        
        return action, log_prob, value.squeeze(-1)
    
    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Evaluate actions for training.
        
        Args:
            obs: [batch_size, obs_dim]
            actions: [batch_size]
        
        Returns:
            log_probs: [batch_size]
            values: [batch_size]
            entropy: [batch_size]
        """
        action_logits, values = self.forward(obs)
        
        dist = torch.distributions.Categorical(logits=action_logits)
        log_probs = dist.log_prob(actions)
        entropy = dist.entropy()
        
        return log_probs, values.squeeze(-1), entropy


class RunningMeanStd:
    """Welford's online algorithm for tracking running mean and variance."""

    def __init__(self, shape=(), clip: float = 10.0):
        self.mean = np.zeros(shape, dtype=np.float64)
        self.var = np.ones(shape, dtype=np.float64)
        self.count = 1e-4
        self.clip = clip

    def update(self, x: np.ndarray):
        batch_mean = np.mean(x, axis=0)
        batch_var = np.var(x, axis=0)
        batch_count = x.shape[0] if x.ndim > 0 else 1
        self._update_from_moments(batch_mean, batch_var, batch_count)

    def _update_from_moments(self, batch_mean, batch_var, batch_count):
        delta = batch_mean - self.mean
        tot_count = self.count + batch_count
        new_mean = self.mean + delta * batch_count / tot_count
        m_a = self.var * self.count
        m_b = batch_var * batch_count
        m2 = m_a + m_b + delta ** 2 * self.count * batch_count / tot_count
        self.mean = new_mean
        self.var = m2 / tot_count
        self.count = tot_count

    def normalize(self, x: np.ndarray) -> np.ndarray:
        return np.clip(
            (x - self.mean) / (np.sqrt(self.var) + 1e-8),
            -self.clip, self.clip
        )


class RolloutBuffer:
    """
    Buffer to store trajectories for PPO training.
    """
    
    def __init__(self, buffer_size: int, obs_dim: int, device: str = 'cpu'):
        self.buffer_size = buffer_size
        self.obs_dim = obs_dim
        self.device = device
        
        # Storage
        self.observations = np.zeros((buffer_size, obs_dim), dtype=np.float32)
        self.actions = np.zeros(buffer_size, dtype=np.int64)
        self.rewards = np.zeros(buffer_size, dtype=np.float32)
        self.values = np.zeros(buffer_size, dtype=np.float32)
        self.log_probs = np.zeros(buffer_size, dtype=np.float32)
        self.dones = np.zeros(buffer_size, dtype=np.float32)
        
        # Computed during finalization
        self.advantages = None
        self.returns = None
        self.old_values = None  # Store old values for clipping
        
        self.ptr = 0
        self.full = False
    
    def add(
        self,
        obs: np.ndarray,
        action: int,
        reward: float,
        value: float,
        log_prob: float,
        done: bool
    ):
        """Add a transition to buffer."""
        self.observations[self.ptr] = obs
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.values[self.ptr] = value
        self.log_probs[self.ptr] = log_prob
        self.dones[self.ptr] = done
        
        self.ptr += 1
        if self.ptr == self.buffer_size:
            self.full = True
            self.ptr = 0
    
    def compute_returns_and_advantages(
        self,
        last_value: float,
        gamma: float,
        gae_lambda: float
    ):
        """
        Compute GAE advantages and returns.
        
        Uses Generalized Advantage Estimation for lower variance.
        """
        size = self.buffer_size if self.full else self.ptr
        
        self.advantages = np.zeros(size, dtype=np.float32)
        self.returns = np.zeros(size, dtype=np.float32)
        self.old_values = self.values[:size].copy()  # Store old values for clipping
        
        last_gae_lam = 0
        for t in reversed(range(size)):
            if t == size - 1:
                next_non_terminal = 1.0 - self.dones[t]
                next_value = last_value
            else:
                next_non_terminal = 1.0 - self.dones[t]
                next_value = self.values[t + 1]
            
            delta = self.rewards[t] + gamma * next_value * next_non_terminal - self.values[t]
            last_gae_lam = delta + gamma * gae_lambda * next_non_terminal * last_gae_lam
            self.advantages[t] = last_gae_lam
        
        self.returns = self.advantages + self.values[:size]
    
    def get_batches(self, batch_size: int):
        """
        Generate random minibatches for training.
        
        Yields:
            Dictionary with batch data
        """
        size = self.buffer_size if self.full else self.ptr
        indices = np.arange(size)
        np.random.shuffle(indices)
        
        for start_idx in range(0, size, batch_size):
            end_idx = min(start_idx + batch_size, size)
            batch_indices = indices[start_idx:end_idx]
            
            yield {
                'observations': torch.from_numpy(self.observations[batch_indices]).to(self.device),
                'actions': torch.from_numpy(self.actions[batch_indices]).to(self.device),
                'old_log_probs': torch.from_numpy(self.log_probs[batch_indices]).to(self.device),
                'old_values': torch.from_numpy(self.old_values[batch_indices]).to(self.device),
                'advantages': torch.from_numpy(self.advantages[batch_indices]).to(self.device),
                'returns': torch.from_numpy(self.returns[batch_indices]).to(self.device),
            }
    
    def clear(self):
        """Reset buffer."""
        self.ptr = 0
        self.full = False
        self.advantages = None
        self.returns = None
        self.old_values = None


class PPOAgent:
    """
    PPO Agent - Core algorithm implementation.
    
    Handles:
    - Policy updates
    - Value function updates
    - Gradient clipping
    - Loss computation
    
    Does NOT handle:
    - Training loops
    - Logging
    - Checkpointing
    - Environment interaction
    """
    
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        config: PPOConfig,
        network_config: Optional[Dict] = None
    ):
        self.config = config
        self.device = torch.device(config.device)
        
        # Create network
        network_config = network_config or {}
        self.network = ActorCriticNetwork(
            obs_dim=obs_dim,
            action_dim=action_dim,
            **network_config
        ).to(self.device)
        
        # print(f"network architecture: {self.network}")
        # Optimizer
        self.optimizer = optim.Adam(
            self.network.parameters(),
            lr=config.learning_rate,
            eps=1e-5
        )
        
        # Rollout buffer
        self.buffer = None

        # Running normalization for observations and rewards
        self.obs_rms = RunningMeanStd(shape=(obs_dim,))
        self.ret_rms = RunningMeanStd(shape=())
        self._normalize_obs = True
        self._normalize_rewards = True
        
        # Training stats
        self.update_count = 0
    
    def create_buffer(self, buffer_size: int, obs_dim: int):
        """Create or reuse rollout buffer."""
        if (self.buffer is not None
                and self.buffer.buffer_size == buffer_size
                and self.buffer.obs_dim == obs_dim):
            self.buffer.clear()
            return
        self.buffer = RolloutBuffer(buffer_size, obs_dim, self.device.type)
    
    def _normalize_observation(self, obs: np.ndarray) -> np.ndarray:
        if self._normalize_obs:
            return self.obs_rms.normalize(obs).astype(np.float32)
        return obs

    def select_action(
        self,
        obs: np.ndarray,
        deterministic: bool = False
    ) -> Tuple[int, float, float]:
        """
        Select action given observation.
        
        Args:
            obs: Observation array
            deterministic: If True, select argmax action
        
        Returns:
            action: Selected action
            value: Value estimate
            log_prob: Log probability of action
        """
        with torch.no_grad():
            norm_obs = self._normalize_observation(obs)
            obs_tensor = torch.from_numpy(norm_obs).float().unsqueeze(0).to(self.device)
            action, log_prob, value = self.network.get_action(obs_tensor, deterministic)
        
        return action.item(), value.item(), log_prob.item()
    
    def select_action_with_confidence(self, obs: np.ndarray, deterministic: bool = False) -> Tuple[int, float, float]:
        """
        Select action given observation with confidence.
        
        Args:
            obs: Observation array
            deterministic: If True, select argmax action
        """
        with torch.no_grad():
            norm_obs = self._normalize_observation(obs)
            obs_tensor = torch.from_numpy(norm_obs).float().unsqueeze(0).to(self.device)
            action, _, _ = self.network.get_action(obs_tensor, deterministic)
            logits, _ = self.network(obs_tensor)
            dist = torch.distributions.Categorical(logits=logits)
            confidence = torch.exp(dist.log_prob(torch.tensor([action]))).item()
        return action.item(), confidence
    
    def update(self, last_value: float) -> Dict[str, float]:
        """
        Perform PPO update.
        
        Args:
            last_value: Value of last state (for GAE computation)
        
        Returns:
            Dictionary of training metrics
        """
        size = self.buffer.buffer_size if self.buffer.full else self.buffer.ptr

        # Update observation running statistics and normalize stored obs
        raw_obs = self.buffer.observations[:size]
        self.obs_rms.update(raw_obs)
        if self._normalize_obs:
            self.buffer.observations[:size] = self.obs_rms.normalize(raw_obs)

        # Normalize rewards using running return std (reward scaling).
        # We track the std of discounted returns and divide rewards by it
        # so that the effective return scale stays ~1 regardless of reward
        # magnitude shifts during training.
        if self._normalize_rewards:
            raw_rewards = self.buffer.rewards[:size]
            self.ret_rms.update(raw_rewards)
            reward_std = np.sqrt(self.ret_rms.var) + 1e-8
            self.buffer.rewards[:size] = raw_rewards / reward_std

        # Compute advantages
        self.buffer.compute_returns_and_advantages(
            last_value=last_value,
            gamma=self.config.gamma,
            gae_lambda=self.config.gae_lambda
        )
        
        # Normalize advantages
        advantages = self.buffer.advantages
        if len(advantages) > 1:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
            advantages = np.clip(advantages, -10.0, 10.0)
        self.buffer.advantages = advantages
        
        # Normalize returns for value loss stability
        returns_raw = self.buffer.returns
        self._ret_mean = float(np.mean(returns_raw))
        self._ret_std = float(np.std(returns_raw)) + 1e-8
        self.buffer.returns = (returns_raw - self._ret_mean) / self._ret_std

        self.buffer.old_values = (self.buffer.old_values - self._ret_mean) / self._ret_std

        # Training loop
        policy_losses = []
        value_losses = []
        entropies = []
        clip_fractions = []
        approx_kls = []

        for epoch in range(self.config.ppo_epochs):
            for batch in self.buffer.get_batches(self.config.minibatch_size):
                log_probs, values_raw, entropy = self.network.evaluate_actions(
                    batch['observations'],
                    batch['actions']
                )

                # Normalise value predictions to match normalised returns
                values = (values_raw - self._ret_mean) / self._ret_std

                # Policy loss (clipped surrogate)
                ratio = torch.exp(log_probs - batch['old_log_probs'])
                surr1 = ratio * batch['advantages']
                surr2 = torch.clamp(
                    ratio,
                    1.0 - self.config.clip_epsilon,
                    1.0 + self.config.clip_epsilon
                ) * batch['advantages']
                policy_loss = -torch.min(surr1, surr2).mean()

                # Value loss — unclipped MSE on normalised returns.
                # Value clipping with clip_epsilon=0.2 is too tight when the
                # return scale changes rapidly; unclipped MSE converges faster.
                value_loss = 0.5 * ((values - batch['returns']) ** 2).mean()

                # Entropy bonus
                entropy_mean = entropy.mean()
                entropy_loss = -entropy_mean

                # Total loss
                loss = (
                    policy_loss
                    + self.config.value_coef * value_loss
                    + self.config.entropy_coef * entropy_loss
                )

                self.optimizer.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(
                    self.network.parameters(),
                    self.config.max_grad_norm
                )
                self.optimizer.step()

                policy_losses.append(policy_loss.item())
                value_losses.append(value_loss.item())
                entropies.append(entropy_mean.item())

                with torch.no_grad():
                    clip_fraction = torch.mean(
                        (torch.abs(ratio - 1.0) > self.config.clip_epsilon).float()
                    ).item()
                    clip_fractions.append(clip_fraction)

                    approx_kl = torch.mean(batch['old_log_probs'] - log_probs).item()
                    approx_kls.append(approx_kl)

            mean_kl = np.mean(approx_kls)
            if mean_kl > 0.02:
                break

        self.update_count += 1

        # Explained variance: how well the value function predicts returns
        # 1.0 = perfect, 0.0 = no better than predicting mean, <0 = worse
        y_true = returns_raw
        y_pred = self.buffer.old_values * self._ret_std + self._ret_mean
        var_y = np.var(y_true)
        explained_var = 1.0 - np.var(y_true - y_pred) / (var_y + 1e-8) if var_y > 1e-8 else 0.0

        return {
            'policy_loss': float(np.mean(policy_losses)),
            'value_loss': float(np.mean(value_losses)),
            'entropy': float(np.mean(entropies)),
            'clip_fraction': float(np.mean(clip_fractions)),
            'approx_kl': float(np.mean(approx_kls)),
            'explained_variance': float(np.clip(explained_var, -1.0, 1.0)),
            'update_count': self.update_count,
        }
    
    def save(self, path: str):
        """
        Save agent checkpoint.

        Writes to a ``*.pt.tmp`` file first, then atomically replaces the
        destination so a concurrent checkpoint-eval worker never reads a
        half-written file.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            'network_state_dict': self.network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'update_count': self.update_count,
            'config': self.config,
            'obs_rms': {'mean': self.obs_rms.mean, 'var': self.obs_rms.var, 'count': self.obs_rms.count},
            'ret_rms': {'mean': self.ret_rms.mean, 'var': self.ret_rms.var, 'count': self.ret_rms.count},
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        torch.save(checkpoint, tmp)
        tmp.replace(path)
    
    def load(self, path: str):
        """Load agent checkpoint."""
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        self.network.load_state_dict(checkpoint['network_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.update_count = checkpoint['update_count']
        if 'obs_rms' in checkpoint:
            self.obs_rms.mean = checkpoint['obs_rms']['mean']
            self.obs_rms.var = checkpoint['obs_rms']['var']
            self.obs_rms.count = checkpoint['obs_rms']['count']
        if 'ret_rms' in checkpoint:
            self.ret_rms.mean = checkpoint['ret_rms']['mean']
            self.ret_rms.var = checkpoint['ret_rms']['var']
            self.ret_rms.count = checkpoint['ret_rms']['count']
        return checkpoint.get('config', self.config)
