"""Unit tests for weak policy (pi0), action space conversion, and smoke test.

Verifies ADR-0007 policy training contracts and SDM Remediation verification.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import torch

from Kodiac_robotics.proof.pi0 import (
    StateDiffusionPolicy,
    StateTrajectoryDataset,
    convert_joint_to_ee_delta,
    run_smoke_test,
)
from Kodiac_robotics.proof.pool import generate_mock_episode


def test_state_diffusion_policy_shapes_and_loss() -> None:
    """Verify Diffusion Policy forward pass and loss computation."""
    obs_dim = 32
    action_dim = 7
    batch_size = 4

    policy = StateDiffusionPolicy(obs_dim=obs_dim, action_dim=action_dim, hidden_dim=64)

    obs = torch.randn(batch_size, obs_dim)
    action = torch.clamp(torch.randn(batch_size, action_dim), -1.0, 1.0)

    loss = policy.compute_loss(obs, action)
    assert loss.dim() == 0
    assert not torch.isnan(loss)
    assert loss.item() > 0.0

    # Test sampling
    sampled = policy.sample_action(obs)
    assert sampled.shape == (batch_size, action_dim)
    assert (sampled >= -1.0).all() and (sampled <= 1.0).all()


def test_trajectory_dataset_loading() -> None:
    """Verify loading from .state.npz files into PyTorch DataLoader."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)

        # Generate 2 mock episodes
        _, path1 = generate_mock_episode(0, "train", True, None, 42, out_dir)
        _, path2 = generate_mock_episode(1, "train", False, "early_open", 43, out_dir)

        dataset = StateTrajectoryDataset([path1, path2])
        assert len(dataset) > 0

        obs_t, act_t = dataset[0]
        assert obs_t.ndim == 1
        assert act_t.shape == (7,)


def test_mandatory_2_episode_smoke_test() -> None:
    """Execute mandatory 2-episode end-to-end policy training smoke test (SDM Remediation)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        episodes_dir = out_dir / "episodes"

        # Generate 2 episodes
        generate_mock_episode(0, "train", True, None, 42, out_dir)
        generate_mock_episode(1, "train", True, None, 43, out_dir)

        result = run_smoke_test(episodes_dir=episodes_dir, num_steps=10)

        assert result["status"] == "passed"
        assert result["episodes_loaded"] == 2
        assert result["total_timesteps"] > 0
        assert result["loss_decreased"] is True
        assert result["sampled_action_shape"] == [4, 7]


def test_convert_joint_to_ee_delta() -> None:
    """Verify joint trajectory conversion to pd_ee_delta_pos."""
    T = 50
    joint_delta = np.random.uniform(-0.1, 0.1, size=(T, 8)).astype(np.float32)
    ee_actions = convert_joint_to_ee_delta(joint_delta)

    assert ee_actions.shape == (T, 7)
    assert (ee_actions >= -1.0).all() and (ee_actions <= 1.0).all()
