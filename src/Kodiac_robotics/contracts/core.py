"""Core data contracts for Kodiac.

Frozen Pydantic v2 schemas and protocols per ARCHITECTURE.md §4 and RULING.md.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

# ==============================================================================
# Enums
# ==============================================================================


class Tri(str, Enum):
    """3-valued Kleene logic tri-state: True (T), False (F), Unknown (U)."""

    T = "T"
    F = "F"
    U = "U"


class Verdict(str, Enum):
    """User-facing overall verdict for a run or step."""

    PASS = "PASS"
    FAIL = "FAIL"
    CANT_TELL = "CANT_TELL"


class ReasonCode(str, Enum):
    """Canonical reason codes required whenever an evaluation yields CANT_TELL."""

    NOT_VISIBLE = "not_visible"
    OCCLUDED = "occluded"
    BELOW_NOISE_FLOOR = "below_noise_floor"
    VIEW_BLOCKED = "view_blocked"
    APPEARANCE_UNRESOLVED = "appearance_unresolved"
    DEPTH_AMBIGUOUS = "depth_ambiguous"


# ==============================================================================
# .green AST Models
# ==============================================================================


class Provenance(BaseModel):
    """Origin and grounding metadata for a step or clause."""

    quote: str | None = None
    t_start: float | None = None
    t_end: float | None = None
    source: Literal["voice", "text", "compiler-default", "user-edit"]


class ObjectDecl(BaseModel):
    """Declaration of an object tracked or tested in a .green specification."""

    name: str
    role: Literal["effector", "rigid", "container", "articulated", "surface"] = "rigid"
    prompt: str | None = None
    aliases: list[str] = Field(default_factory=list)
    size_cm: float | None = None
    height_cm: float | None = None

    @model_validator(mode="before")
    @classmethod
    def _apply_role_defaults(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Reserved object name `gripper` defaults to role="effector" unless explicitly declared
            if data.get("name") == "gripper" and "role" not in data:
                data["role"] = "effector"
        return data


class Param(BaseModel):
    """Numerical threshold parameter comparison."""

    name: str
    op: Literal["=", "<=", ">="]
    value: float


class Atom(BaseModel):
    """Atomic predicate, visual check, or manual assertion."""

    kind: Literal["pred", "looks", "manual"]
    name: Literal["on", "inside", "near", "lifted", "moves_with", "dwell"] | None = None
    args: list[str] = Field(default_factory=list)
    params: list[Param] = Field(default_factory=list)
    looks_pos: str | None = None
    looks_neg: str | None = None
    manual_text: str | None = None


class Expr(BaseModel):
    """Boolean expression tree over Atoms."""

    op: Literal["and", "or", "not", "atom"]
    children: list[Expr] = Field(default_factory=list)
    atom: Atom | None = None


class Step(BaseModel):
    """One sequential step in a .green specification."""

    index: int
    name: str
    expr: Expr
    provenance: Provenance
    extra_provenance: list[Provenance] = Field(default_factory=list)


class GreenTest(BaseModel):
    """Parsed and validated .green test specification."""

    version: Literal["0.1"] = "0.1"
    name: str
    objects: list[ObjectDecl]
    steps: list[Step]
    params: list[Param] = Field(default_factory=list)
    header_comment: str | None = None


class GreenLock(BaseModel):
    """Sidecar lock file (<name>.green.lock) binding test to calibration baselines."""

    model_config = {"protected_namespaces": ()}

    test_sha256: str
    transcript: list[dict[str, Any]]
    object_baselines: dict[str, dict[str, Any]]  # A0, k0, rim ellipse, scores
    demo_events: list[Event]
    geometry_tier: Literal["A", "B", "C"]
    model_ids: dict[str, str]
    created_at: str


# ==============================================================================
# Perception & Video Models
# ==============================================================================


class ClipRef(BaseModel):
    """Reference to an input video clip or robotic episode."""

    uri: str
    source_kind: Literal["real", "sim", "upload", "demo"]
    dataset: str | None = None
    episode_index: int | None = None
    camera: str | None = None


class Clip(BaseModel):
    """Normalized video clip container."""

    ref: ClipRef
    path_h264: str
    fps: float
    n_frames: int
    width: int
    height: int
    sha256: str


class ObjMask(BaseModel):
    """Mask annotation for a single object in a single frame."""

    obj: str
    frame: int
    score: float
    bbox_xyxy: tuple[float, float, float, float]
    rle: str
    area_px: int
    rle_size: tuple[int, int] = (0, 0)


class Track(BaseModel):
    """Temporal sequence of object masks across frames."""

    obj: str
    frames: dict[int, ObjMask]
    backend: Literal["api", "modal", "fixture"]
    direction: str
    trace_id: str


# ==============================================================================
# Protocols
# ==============================================================================


class Segmenter(Protocol):
    """Protocol for segmentation and spatio-temporal tracking backends."""

    def segment_frames(
        self,
        clip: Clip,
        frames: list[int],
        prompts: dict[str, list[str]],
    ) -> dict[str, Track]: ...

    def track(
        self,
        clip: Clip,
        f0: int,
        f1: int,
        seeds: dict[str, ObjMask],
        direction: Literal["forward", "backward", "both"],
    ) -> dict[str, Track]: ...


class VLMJudge(Protocol):
    """Protocol for VLM two-way question adjudication."""

    def ask_two_way(self, crop_png: bytes, q_pos: str, q_neg: str) -> tuple[Tri, str]: ...


class ASR(Protocol):
    """Protocol for speech transcription."""

    def transcribe(self, wav_path: str) -> list[dict[str, Any]]: ...


class Memory(Protocol):
    """Protocol for persistent execution memory."""

    def load(self) -> dict[str, Any]: ...
    def save(self, state: dict[str, Any]) -> None: ...


class ScaleModel(Protocol):
    """Protocol for metric scale recovery and world coordinate mapping."""

    tier: Literal["A", "B", "C"]

    def to_table_frame(
        self,
        obj: str,
        frame: int,
    ) -> tuple[float, float, float, float]: ...


# ==============================================================================
# Measurement & Blame Models
# ==============================================================================


class Component(BaseModel):
    """Physical component measurement with uncertainty and margin."""

    name: str  # e.g. "on.align_xy"
    value: float
    threshold: float
    margin: float
    sigma: float
    unit: Literal["cm", "s", "ratio", "cm/s"]
    tri: Tri
    reason: ReasonCode | None = None


class PredFrame(BaseModel):
    """Per-frame evaluated predicate state."""

    frame: int
    atom_key: str
    tri: Tri
    components: list[Component]
    trace_id: str


class Event(BaseModel):
    """Physical transition or discrete event."""

    step: int
    step_name: str
    kind: Literal[
        "achieved",
        "failed",
        "grasped",
        "lifted",
        "contacted",
        "released",
        "entered",
        "settled",
        "broke",
        "order_violation",
    ]
    predicate: str | None = None
    args: list[str] = Field(default_factory=list)
    t_s: float
    frame: int
    fps: float
    measurements: dict[str, tuple[float, float]] = Field(default_factory=dict)
    source: Literal["demo", "attempt"]
    verdict: Verdict | None = None


class StepResult(BaseModel):
    """Outcome of a single sequential step in a run."""

    index: int
    name: str
    verdict: Verdict | None = None  # None = not evaluated
    t_s: float | None = None
    frame: int | None = None
    decisive: list[Component] = Field(default_factory=list)
    reasons: list[ReasonCode] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class CodeLocation(BaseModel):
    """Source code mapping for an identified failure."""

    file: str
    line: int
    code: str
    span_id: int


class Hint(BaseModel):
    """Actionable numerical guidance for policy or script adjustment."""

    variable: str
    delta: float | list[float] | None = None
    unit: str | None = None
    move: str | None = None
    basis: str


class FactTable(BaseModel):
    """Rigorous physical facts established at failure onset frame t*."""

    t_star_s: float
    frame: int
    fps: float
    sigma_frames: float
    step_index: int
    step_name: str
    literal: str
    transition: Literal["T->F", "never_T", "order", "unmet"]
    facts: dict[str, dict[str, Any]]
    dataset_index: int | None = None
    action_chunk: int | None = None
    code_location: CodeLocation | None = None
    evidence: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)


class Blame(BaseModel):
    """Full causal attribution for a failed test execution."""

    facts: FactTable
    summary: str
    summary_source: Literal["muse-spark", "template"]
    hint: Hint | None = None
    warnings: list[str] = Field(default_factory=list)


# ==============================================================================
# Run & Loop Models
# ==============================================================================

_NONCE_REGEX = re.compile(r"^[0-9a-f]{16}$")


class RunResult(BaseModel):
    """Complete, immutable output of a Kodiac run evaluation."""

    run_id: str
    test_name: str
    test_sha256: str
    config_sha256: str
    clip: ClipRef
    verdict: Verdict
    exit_code: Literal[0, 1, 2, 3]
    steps: list[StepResult] = Field(default_factory=list)
    reasons: list[ReasonCode] = Field(default_factory=list)
    blame: Blame | None = None
    diff_text: str | None = None
    events: list[Event] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    backends: dict[str, str] = Field(default_factory=dict)
    badges: list[str] = Field(default_factory=list)
    nonce: str
    is_fixture: bool = False
    card_path: str | None = None
    trace_path: str
    created_at: str

    @field_validator("nonce")
    @classmethod
    def _validate_nonce_format(cls, v: str) -> str:
        if not _NONCE_REGEX.match(v):
            raise ValueError(f"Nonce must be a 16-character lowercase hex string, got: {v}")
        return v

    @field_validator("timings_ms")
    @classmethod
    def _validate_timings(cls, v: dict[str, int]) -> dict[str, int]:
        for key, val in v.items():
            if val < 0:
                raise ValueError(f"Timing '{key}' cannot be negative, got {val}")
        return v

    @model_validator(mode="after")
    def _validate_cant_tell_reasons(self) -> RunResult:
        if self.verdict == Verdict.CANT_TELL and not self.reasons:
            raise ValueError("Verdict.CANT_TELL requires at least one ReasonCode in reasons")
        return self


class VerifyRequest(BaseModel):
    """Input payload for Kodiac verification operations."""

    test: str
    sim_script: str | None = None
    seed: int = 0
    clip: str | None = None
    mode: Literal["fast", "full"] = "full"
    fresh: bool = True


class GateState(BaseModel):
    """Persisted state for the Kodiac done-gate."""

    pinned_test_sha256: str
    pinned_config_sha256: str
    blocks: int
    max_blocks: int
    last_nonce: str | None = None


# ==============================================================================
# Audit & Proof Models
# ==============================================================================


class VerdictRow(BaseModel):
    """Row schema for batch audit parquet export."""

    model_config = {"protected_namespaces": ()}

    dataset: str
    episode_index: int
    camera: str
    verdict: Verdict
    t_star_s: float | None = None
    frame: int | None = None
    step: str | None = None
    predicate: str | None = None
    margin: float | None = None
    sigma: float | None = None
    reasons: list[str] = Field(default_factory=list)
    evidence_uri: str | None = None
    model_ids: str
    Kodiac_version: str
    human_verified: bool | None = None


class JudgeLabel(BaseModel):
    """Label for judge pool benchmarking."""

    judge: str
    episode_id: str
    accept: bool
    score: float | None = None
    verdict: Verdict | None = None
    latency_ms: int
    cost_usd: float
    calibration_threshold: float | None = None


# ==============================================================================
# Rebuild Forward References
# ==============================================================================

Expr.model_rebuild()
GreenLock.model_rebuild()
