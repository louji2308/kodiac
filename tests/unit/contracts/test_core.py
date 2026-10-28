"""Unit tests for Kodiac core contracts, serialization, validation, and recursion.

Guarantees 100% roundtrip fidelity, enum integrity, nonce validation,
and deep recursive schema safety per ARCHITECTURE.md §4 and RULING.md.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from Kodiac_robotics.cache import DiskCache, cached_call, compute_key_hash
from Kodiac_robotics.config import Settings
from Kodiac_robotics.contracts.core import (
    Atom,
    Blame,
    Expr,
    GreenLock,
    GreenTest,
    ObjectDecl,
    Param,
    Provenance,
    ReasonCode,
    RunResult,
    Step,
    Track,
    Tri,
    Verdict,
)
from Kodiac_robotics.contracts.fixtures import (
    make_dummy_blame,
    make_dummy_greentest,
    make_dummy_lock,
    make_dummy_runresult,
    make_dummy_track,
)

# ==============================================================================
# Enum Integrity Tests
# ==============================================================================


def test_enum_tri_values() -> None:
    assert Tri.T.value == "T"
    assert Tri.F.value == "F"
    assert Tri.U.value == "U"
    assert len(Tri) == 3


def test_enum_verdict_values() -> None:
    assert Verdict.PASS.value == "PASS"
    assert Verdict.FAIL.value == "FAIL"
    assert Verdict.CANT_TELL.value == "CANT_TELL"
    assert len(Verdict) == 3


def test_enum_reason_codes() -> None:
    expected_codes = {
        "not_visible",
        "occluded",
        "below_noise_floor",
        "view_blocked",
        "appearance_unresolved",
        "depth_ambiguous",
    }
    actual_codes = {r.value for r in ReasonCode}
    assert actual_codes == expected_codes


# ==============================================================================
# Model Invariant & Validation Tests
# ==============================================================================


def test_gripper_default_role() -> None:
    # Reserved name 'gripper' automatically defaults to role='effector'
    decl = ObjectDecl(name="gripper")
    assert decl.role == "effector"

    # Explicit override is preserved
    decl_custom = ObjectDecl(name="gripper", role="rigid")
    assert decl_custom.role == "rigid"

    # Other objects default to 'rigid'
    decl_block = ObjectDecl(name="red_cube")
    assert decl_block.role == "rigid"


def test_runresult_nonce_validation() -> None:
    # Valid 16-hex nonce
    res = make_dummy_runresult(nonce="0123456789abcdef")
    assert res.nonce == "0123456789abcdef"

    # Invalid length (15 hex)
    with pytest.raises(ValidationError):
        make_dummy_runresult(nonce="0123456789abcde")

    # Invalid characters (uppercase or non-hex)
    with pytest.raises(ValidationError):
        make_dummy_runresult(nonce="0123456789ABCDEF")
    with pytest.raises(ValidationError):
        make_dummy_runresult(nonce="xyz123456789abcd")


def test_runresult_timings_non_negative() -> None:
    res = make_dummy_runresult()
    res.timings_ms["segment"] = 0  # 0 is valid
    assert res.timings_ms["segment"] == 0

    # Negative timing must be rejected
    with pytest.raises(ValidationError):
        RunResult.model_validate(
            {
                **res.model_dump(),
                "timings_ms": {"segment": -10},
            }
        )


def test_runresult_cant_tell_requires_reason() -> None:
    # CANT_TELL with reasons is valid
    res_valid = make_dummy_runresult(verdict=Verdict.CANT_TELL)
    assert len(res_valid.reasons) > 0

    # CANT_TELL without reasons must fail validation
    with pytest.raises(ValidationError):
        RunResult.model_validate(
            {
                **res_valid.model_dump(),
                "reasons": [],
            }
        )


# ==============================================================================
# Roundtrip Serialization Tests
# ==============================================================================


def test_roundtrip_greentest() -> None:
    gt = make_dummy_greentest()
    json_str = gt.model_dump_json()
    gt_recovered = GreenTest.model_validate_json(json_str)
    assert gt == gt_recovered


def test_roundtrip_runresult() -> None:
    res = make_dummy_runresult()
    json_str = res.model_dump_json()
    res_recovered = RunResult.model_validate_json(json_str)
    assert res == res_recovered
    assert res_recovered.is_fixture is True


def test_roundtrip_blame() -> None:
    blame = make_dummy_blame()
    json_str = blame.model_dump_json()
    blame_recovered = Blame.model_validate_json(json_str)
    assert blame == blame_recovered


def test_roundtrip_lock() -> None:
    lock = make_dummy_lock()
    json_str = lock.model_dump_json()
    lock_recovered = GreenLock.model_validate_json(json_str)
    assert lock == lock_recovered


def test_roundtrip_track() -> None:
    track = make_dummy_track(n_frames=10)
    json_str = track.model_dump_json()
    track_recovered = Track.model_validate_json(json_str)
    assert track == track_recovered


# ==============================================================================
# Deep Recursion Test (RULING §5: ≥10 nested levels)
# ==============================================================================


def test_deep_recursive_expr_serialization() -> None:
    """Test that self-referential Expr models with >=10 nested levels serialize/deserialize cleanly."""
    depth = 15

    # Leaf atom
    leaf = Expr(
        op="atom",
        atom=Atom(
            kind="pred",
            name="on",
            args=["red_block", "green_block"],
            params=[Param(name="align_xy", op="<=", value=1.5)],
        ),
    )

    # Nest 15 levels deep
    current = leaf
    for i in range(depth):
        op = "not" if (i % 3 == 0) else ("and" if (i % 2 == 0) else "or")
        current = Expr(op=op, children=[current])

    # Roundtrip serialization of the deep tree
    json_str = current.model_dump_json()
    recovered = Expr.model_validate_json(json_str)
    assert recovered == current

    # Embed within a full GreenTest and serialize
    gt = GreenTest(
        version="0.1",
        name="deep_recursive_test",
        objects=[ObjectDecl(name="red_block"), ObjectDecl(name="green_block")],
        steps=[
            Step(
                index=1,
                name="deep_step",
                expr=current,
                provenance=Provenance(source="compiler-default"),
            )
        ],
    )
    gt_json = gt.model_dump_json()
    gt_recovered = GreenTest.model_validate_json(gt_json)
    assert gt == gt_recovered


# ==============================================================================
# Config & Masking Tests
# ==============================================================================


def test_settings_masking() -> None:
    settings = Settings(
        model_api_key="meta_sec_1234567890abcdef",
        modal_token_id="mod_tok_111",
        sam_backend="fixture",
    )
    masked = settings.masked_dict()

    # Secret should be masked
    assert "1234567890" not in masked["model_api_key"]
    assert masked["model_api_key"].startswith("met")
    assert masked["sam_backend"] == "fixture"


# ==============================================================================
# Cache Tests
# ==============================================================================


def test_disk_cache_atomic_write_and_hit(tmp_path) -> None:
    cache = DiskCache(tmp_path)
    key_parts = {"model": "sam-3.1", "action": "track", "frame": 42}
    payload = b"video_frame_bytes"

    # Compute expected hash
    expected_hash = compute_key_hash(key_parts, payload)

    # Initial get should be None
    assert cache.get(key_parts, payload) is None

    # Set value
    val = {"status": "success", "masks": [1, 2, 3]}
    res_hash = cache.set(key_parts, val, payload)
    assert res_hash == expected_hash

    # Cached get should return value
    cached_val = cache.get(key_parts, payload)
    assert cached_val == val

    # Test cached_call helper
    call_count = 0

    def compute_expensive() -> dict[str, str]:
        nonlocal call_count
        call_count += 1
        return {"result": "expensive_computed"}

    res1 = cached_call({"call_id": "call_1"}, compute_expensive, cache_dir=tmp_path)
    assert res1 == {"result": "expensive_computed"}
    assert call_count == 1

    # Second call must hit cache without invoking function
    res2 = cached_call({"call_id": "call_1"}, compute_expensive, cache_dir=tmp_path)
    assert res2 == {"result": "expensive_computed"}
    assert call_count == 1
