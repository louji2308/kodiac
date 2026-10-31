"""Unit tests for audit trace writer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import orjson

from Kodiac_robotics.contracts.core import Component, Event, PredFrame, Tri
from Kodiac_robotics.engine.trace import TraceWriter


def test_trace_writer_lifecycle_and_serialization() -> None:
    """Verify writing events and predicate frames produces valid JSONL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        trace_file = Path(tmpdir) / "runs" / "test_run" / "trace.jsonl"
        with TraceWriter(trace_file) as writer:
            event = Event(
                step=0,
                step_name="grasp",
                kind="grasped",
                predicate="moves_with",
                args=["gripper", "cubeA"],
                t_s=1.2,
                frame=36,
                fps=30.0,
                source="attempt",
            )
            writer.write_event(event)

            comp = Component(
                name="moves_with.gripper.cubeA",
                value=0.5,
                threshold=1.5,
                margin=1.0,
                sigma=0.2,
                unit="cm",
                tri=Tri.T,
            )
            pred_frame = PredFrame(
                frame=36,
                atom_key="moves_with(gripper, cubeA)",
                tri=Tri.T,
                components=[comp],
                trace_id="tr_test_123",
            )
            writer.write_pred_frame(36, "moves_with", pred_frame)

        assert trace_file.is_file()
        lines = [line.strip() for line in trace_file.read_bytes().splitlines() if line.strip()]
        assert len(lines) == 2

        rec0 = orjson.loads(lines[0])
        assert rec0["record_type"] == "event"
        assert rec0["data"]["kind"] == "grasped"
        assert rec0["data"]["step_name"] == "grasp"

        rec1 = orjson.loads(lines[1])
        assert rec1["record_type"] == "pred_frame"
        assert rec1["frame"] == 36
        assert rec1["atom"] == "moves_with"
        assert rec1["tri"] == "T"
        assert len(rec1["components"]) == 1
        assert rec1["components"][0]["name"] == "moves_with.gripper.cubeA"
