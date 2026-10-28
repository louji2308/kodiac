"""Deterministic bug definitions and patch registry for Franka Panda StackCube.

Defines B01–B10 bugs with expected failure steps, predicates, and blame spans.
Per ARCHITECTURE.md §4, §5.7, ADR-0005, and P02 RULING.
"""

from __future__ import annotations

from pydantic import BaseModel

from Kodiac_robotics.sim.spans import ActuationClass


class BugDef(BaseModel):
    """Specification of a deterministic bug injection in pick-and-place."""

    id: str  # "B01" ... "B10"
    name: str
    description: str
    patch_path: str
    expected_failure_step: int
    expected_broken_predicate: str
    expected_blame_span: ActuationClass
    expected_oracle_success: bool = False
    spoken_instruction: str
    diagnostic_hint: str


BUGS: dict[str, BugDef] = {
    "B01": BugDef(
        id="B01",
        name="early_release",
        description="Opens gripper prematurely while in transit to the target cube, dropping it mid-table.",
        patch_path="examples/sim/bugs/B01.patch",
        expected_failure_step=3,
        expected_broken_predicate="moves_with",
        expected_blame_span="gripper.open",
        expected_oracle_success=False,
        spoken_instruction="Pick up the red cube and stack it onto the green cube.",
        diagnostic_hint="Gripper opened early while moving towards the target block.",
    ),
    "B02": BugDef(
        id="B02",
        name="xy_offset",
        description="Releases cube with excessive 5 cm XY offset, missing the target cube top surface.",
        patch_path="examples/sim/bugs/B02.patch",
        expected_failure_step=4,
        expected_broken_predicate="on",
        expected_blame_span="arm.move_to",
        expected_oracle_success=False,
        spoken_instruction="Stack the red cube squarely on top of the green cube.",
        diagnostic_hint="End effector released cube with excessive XY offset from the target.",
    ),
    "B03": BugDef(
        id="B03",
        name="low_lift",
        description="Lifts cube by only 0.5 cm, causing a horizontal obstacle collision with the green cube.",
        patch_path="examples/sim/bugs/B03.patch",
        expected_failure_step=2,
        expected_broken_predicate="lifted",
        expected_blame_span="arm.lift",
        expected_oracle_success=False,
        spoken_instruction="Lift the red cube cleanly to clear obstacles and place it on the green cube.",
        diagnostic_hint="Lift height was insufficient to clear obstacles.",
    ),
    "B04": BugDef(
        id="B04",
        name="short_dwell",
        description="Dwells for only 0.03s after release, immediately retracting and violating settling velocity check.",
        patch_path="examples/sim/bugs/B04.patch",
        expected_failure_step=4,
        expected_broken_predicate="dwell",
        expected_blame_span="wait",
        expected_oracle_success=False,
        spoken_instruction="Place the red cube on the green cube and hold until it is completely stationary.",
        diagnostic_hint="Retracted immediately without allowing object to settle.",
    ),
    "B05": BugDef(
        id="B05",
        name="lift_before_close",
        description="Lifts arm before closing the gripper jaws, leaving the red cube behind on the table.",
        patch_path="examples/sim/bugs/B05.patch",
        expected_failure_step=2,
        expected_broken_predicate="moves_with",
        expected_blame_span="arm.lift",
        expected_oracle_success=False,
        spoken_instruction="Close the gripper around the red cube before lifting.",
        diagnostic_hint="Arm attempted to lift before gripper closed around object.",
    ),
    "B06": BugDef(
        id="B06",
        name="high_grasp",
        description="Descends to 7 cm above the cube, closing the gripper on empty air above the object.",
        patch_path="examples/sim/bugs/B06.patch",
        expected_failure_step=2,
        expected_broken_predicate="lifted",
        expected_blame_span="arm.move_to",
        expected_oracle_success=False,
        spoken_instruction="Descend fully to grasp the red cube at tabletop height.",
        diagnostic_hint="Gripper closed above object height, failing to grasp.",
    ),
    "B07": BugDef(
        id="B07",
        name="missing_close",
        description="Omits gripper.close() entirely, moving the open gripper across the workspace empty-handed.",
        patch_path="examples/sim/bugs/B07.patch",
        expected_failure_step=2,
        expected_broken_predicate="moves_with",
        expected_blame_span="arm.move_to",
        expected_oracle_success=False,
        spoken_instruction="Grasp and stack the red cube on the green cube.",
        diagnostic_hint="Gripper was never closed before moving.",
    ),
    "B08": BugDef(
        id="B08",
        name="wrong_object",
        description="Navigates to the wrong tabletop coordinates, failing proximity to the target red cube.",
        patch_path="examples/sim/bugs/B08.patch",
        expected_failure_step=1,
        expected_broken_predicate="near",
        expected_blame_span="arm.move_to",
        expected_oracle_success=False,
        spoken_instruction="Move to the red cube.",
        diagnostic_hint="Robot navigated to incorrect coordinates instead of target block.",
    ),
    "B09": BugDef(
        id="B09",
        name="never_opens",
        description="Fails to open gripper at placement pose, dragging the cube away during arm retraction.",
        patch_path="examples/sim/bugs/B09.patch",
        expected_failure_step=4,
        expected_broken_predicate="on",
        expected_blame_span="arm.retract",
        expected_oracle_success=False,
        spoken_instruction="Release the red cube once it is positioned on the green cube.",
        diagnostic_hint="Gripper never released block after positioning.",
    ),
    "B10": BugDef(
        id="B10",
        name="high_release",
        description="Opens gripper 15 cm above target cube; free-fall impact causes bounce and toppling.",
        patch_path="examples/sim/bugs/B10.patch",
        expected_failure_step=4,
        expected_broken_predicate="on",
        expected_blame_span="gripper.open",
        expected_oracle_success=False,
        spoken_instruction="Lower the red cube gently onto the green cube before opening the gripper.",
        diagnostic_hint="Gripper opened at excessive height above target, causing block to tumble.",
    ),
}


def get_bug(bug_id: str) -> BugDef:
    """Retrieve bug definition by ID (e.g. 'B01')."""
    if bug_id not in BUGS:
        raise KeyError(f"Unknown bug ID '{bug_id}'. Available: {list(BUGS.keys())}")
    return BUGS[bug_id]


def list_bugs() -> list[BugDef]:
    """Return all 10 registered bug definitions."""
    return list(BUGS.values())
