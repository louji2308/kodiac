"""Simulation harness: KinematicMockEnv, ManiSkillEnv, and span/bug registry.

Per ARCHITECTURE.md §4, §5.7, ADR-0004, ADR-0005, ADR-0007, and P02 RULING.
"""

from Kodiac_robotics.sim.bugs import BUGS, BugDef, get_bug, list_bugs
from Kodiac_robotics.sim.env import KinematicMockEnv, ManiSkillEnv, SimEnv, SimRun, SimState
from Kodiac_robotics.sim.robot import ArmController, GripperController, RobotController
from Kodiac_robotics.sim.spans import ActuationClass, SimSpan, find_blame_span, span
from Kodiac_robotics.sim.video import save_sim_run, write_video_cfr_30fps

__all__ = [
    "SimEnv",
    "KinematicMockEnv",
    "ManiSkillEnv",
    "SimState",
    "SimRun",
    "SimSpan",
    "ActuationClass",
    "span",
    "find_blame_span",
    "RobotController",
    "ArmController",
    "GripperController",
    "BugDef",
    "BUGS",
    "get_bug",
    "list_bugs",
    "save_sim_run",
    "write_video_cfr_30fps",
]
