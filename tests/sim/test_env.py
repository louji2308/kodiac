"""Unit tests for simulation environment backends and state/video serialization.

Per ARCHITECTURE.md §4, §5.7, ADR-0004, ADR-0007, and P02 RULING.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from Kodiac_robotics.sim.env import KinematicMockEnv, ManiSkillEnv, SimEnv, SimState
from Kodiac_robotics.sim.video import save_sim_run


def test_kinematic_mock_env_offline_contract() -> None:
    """Verify KinematicMockEnv satisfies SimEnv protocol and runs 100% offline."""
    env: SimEnv = KinematicMockEnv()
    assert env.backend == "kinematic_mock"
    assert env.is_mock is True

    obs, info = env.reset(seed=42)
    assert isinstance(obs, np.ndarray)
    assert obs.dtype == np.float32
    assert obs.shape == (13,)
    assert info.get("is_mock") is True
    assert info.get("env_backend") == "kinematic_mock"

    # Single step
    action = np.zeros(7, dtype=np.float32)
    obs, reward, term, trunc, step_info = env.step(action)
    assert obs.shape == (13,)
    assert isinstance(reward, float)
    assert term is False
    assert trunc is False
    assert "oracle_success" in step_info


def test_kinematic_mock_privileged_state() -> None:
    """Verify privileged_state returns valid SimState model."""
    env = KinematicMockEnv()
    env.reset(seed=123)
    state = env.privileged_state()
    assert isinstance(state, SimState)
    assert state.step == 0
    assert state.t_s == 0.0
    assert len(state.cubeA_pose) == 7
    assert len(state.cubeB_pose) == 7
    assert len(state.cubeA_vel) == 3
    assert isinstance(state.in_contact, bool)


def test_law1_watermark_banner() -> None:
    """Law 1 Anti-Fabrication: render must indelibly burn [MOCK SIMULATION · NOT SAPIEN PHYSICS]."""
    env = KinematicMockEnv()
    env.reset(seed=1)
    frame = env.render()
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (512, 512, 3)
    assert frame.dtype == np.uint8

    # Top banner bar (y in 0..32) must be dark background with bright text
    banner_bar = frame[0:30, :, :]
    # Mean luminance should reflect black bar with red/orange text
    assert banner_bar.mean() > 10.0  # Has text drawn
    assert banner_bar.mean() < 80.0  # Bar is mostly dark grey/black


def test_state_npz_contract_adr0007() -> None:
    """Verify .state.npz contains actions (T, 7), obs_state (T, d), cam_K (3, 3), cam_extrinsic (4, 4)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        env = KinematicMockEnv()
        env.reset(seed=99)

        frames = [env.render() for _ in range(5)]
        states = [env.privileged_state() for _ in range(5)]
        actions = np.zeros((5, 7), dtype=np.float32)
        obs_states = np.zeros((5, 13), dtype=np.float32)

        run = save_sim_run(
            output_dir=out_dir,
            run_id="test_ep_001",
            frames=frames,
            states=states,
            actions=actions,
            obs_states=obs_states,
            cam_K=env.cam_K,
            cam_extrinsic=env.cam_extrinsic,
            spans=[],
            oracle_success=False,
            seed=99,
            backend=env.backend,
            is_mock=env.is_mock,
        )

        assert Path(run.video_path).is_file()
        assert Path(run.state_path).is_file()
        assert Path(run.meta_path).is_file()

        with np.load(run.state_path) as data:
            assert "actions" in data
            assert data["actions"].shape == (5, 7)
            assert data["actions"].dtype == np.float32

            assert "obs_state" in data
            assert data["obs_state"].shape == (5, 13)

            assert "cam_K" in data
            assert data["cam_K"].shape == (3, 3)

            assert "cam_extrinsic" in data
            assert data["cam_extrinsic"].shape == (4, 4)


def test_maniskill_lazy_import_isolation() -> None:
    """Verify ManiSkillEnv isolates mani_skill import and raises descriptive error when missing."""
    try:
        import mani_skill  # noqa: F401
        has_maniskill = True
    except ImportError:
        has_maniskill = False

    if not has_maniskill:
        with pytest.raises(RuntimeError, match="ManiSkill/SAPIEN is not installed"):
            ManiSkillEnv()
