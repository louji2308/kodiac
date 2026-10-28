"""Export JSON Schemas for all core Pydantic models to docs/schemas/."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from Kodiac_robotics.contracts.core import (
    Atom,
    Blame,
    Clip,
    ClipRef,
    CodeLocation,
    Component,
    Event,
    Expr,
    FactTable,
    GateState,
    GreenLock,
    GreenTest,
    Hint,
    JudgeLabel,
    ObjectDecl,
    ObjMask,
    Param,
    PredFrame,
    Provenance,
    RunResult,
    Step,
    StepResult,
    Track,
    VerdictRow,
    VerifyRequest,
)

CORE_MODELS: list[Type[BaseModel]] = [
    Provenance,
    ObjectDecl,
    Param,
    Atom,
    Expr,
    Step,
    GreenTest,
    GreenLock,
    ClipRef,
    Clip,
    ObjMask,
    Track,
    Component,
    PredFrame,
    Event,
    StepResult,
    CodeLocation,
    Hint,
    FactTable,
    Blame,
    RunResult,
    VerifyRequest,
    GateState,
    VerdictRow,
    JudgeLabel,
]


def export_schemas(output_dir: Path | str = "docs/schemas") -> dict[str, Path]:
    """Export JSON schema for each core model into output_dir.

    Returns mapping of model name to generated schema file path.
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    generated: dict[str, Path] = {}
    index_manifest: dict[str, str] = {}

    for model in CORE_MODELS:
        name = model.__name__
        schema = model.model_json_schema()
        target_file = out_path / f"{name}.json"
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(schema, f, indent=2)
            f.write("\n")
        generated[name] = target_file
        index_manifest[name] = f"{name}.json"

    # Write manifest index
    with open(out_path / "index.json", "w", encoding="utf-8") as f:
        json.dump(index_manifest, f, indent=2)
        f.write("\n")

    return generated


def main() -> None:
    parser = argparse.ArgumentParser(description="Export Kodiac Pydantic JSON schemas.")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="docs/schemas",
        help="Target directory for schema files (default: docs/schemas)",
    )
    args = parser.parse_args()
    results = export_schemas(args.output_dir)
    print(f"Exported {len(results)} JSON schemas to {args.output_dir}/")


if __name__ == "__main__":
    main()
