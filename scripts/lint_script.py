"""Lint a video script against IDEA.md section 10.3 (voiceover discipline).

Usage: python scripts/lint_script.py video/SCRIPT.md [--concepts video/concepts.yaml]
                                      [--root .] [--json]

Script format (see video/SCRIPT.md):
    ## 0:00-0:12 [C1]
    VO: spoken words
    SCREEN: on-screen text / visuals

Exit codes: 0 clean, 1 violations, 2 setup error / unverifiable only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TAGLINE = "Robots can finally fail a test."
MAX_CONCEPTS = 8
MAX_SECONDS = 180
WPM = 150
HOOK_SECONDS = 5
PENDING = "[MEASURED VALUE PENDING]"

BEAT_RE = re.compile(r"^##\s+(\d+):(\d{2})\s*[-\u2013]\s*(\d+):(\d{2})\s*((?:\[C\d+\]\s*)*)\s*$")
NAME_RE = re.compile(r"SAM 3\.1|ManiSkill3|Muse \w+ ?\d*(?:\.\d+)?", re.I)
NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%?")


class LintSetupError(Exception):
    pass


def parse_banned_words(idea_text: str) -> list[str]:
    """Read the banned list out of IDEA.md section 10.3 so it cannot drift."""
    m = re.search(r"\*\*Banned spoken/on-screen words:\*\*(.*?)(?:\n\s*\n|\n- )", idea_text, re.S)
    if not m:
        raise LintSetupError("banned-word list not found in IDEA.md section 10.3")
    body = " ".join(m.group(1).split())
    body = body.split("plus every term")[0]
    words = []
    for raw in body.split("\u00b7"):
        w = raw.replace("**", "").strip().strip(".").strip()
        w = w.strip('"').strip("\u201c\u201d").strip()
        if w:
            words.append(w)
    if len(words) < 5:
        raise LintSetupError(f"banned-word list parse looks wrong: {words}")
    return words


def parse_numbers_registry(text: str) -> dict[str, str]:
    """Map every numeric token found in the Registered Value column -> row status."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0].lower() == "item":
            continue
        status = cells[-1]
        for tok in NUM_RE.findall(cells[1]):
            out[tok.rstrip("%")] = status
    return out


def parse_beats(script: str) -> list[dict]:
    beats: list[dict] = []
    cur: dict | None = None
    for ln, line in enumerate(script.splitlines(), 1):
        m = BEAT_RE.match(line.strip())
        if m:
            h1, m1, h2, m2, tags = m.groups()
            cur = {
                "start": int(h1) * 60 + int(m1),
                "end": int(h2) * 60 + int(m2),
                "concepts": re.findall(r"C\d+", tags),
                "vo": [],
                "screen": [],
                "line": ln,
            }
            beats.append(cur)
        elif cur is not None:
            s = line.strip()
            if s.upper().startswith("VO:"):
                cur["vo"].append((ln, s[3:].strip()))
            elif s.upper().startswith("SCREEN:"):
                cur["screen"].append((ln, s[7:].strip()))
    return beats


def _load_concepts(path: Path) -> list[dict]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = data.get("concepts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise LintSetupError(f"{path}: expected a list under 'concepts'")
    return items


def lint(script_path: Path, concepts_path: Path, root: Path) -> dict:
    violations: list[dict] = []
    unverifiable: list[str] = []

    def v(rule: str, msg: str, line: int | None = None) -> None:
        violations.append({"rule": rule, "line": line, "message": msg})

    idea = root / "docs" / "architecture" / "IDEA.md"
    if not idea.exists():
        idea = root / "IDEA.md"
    if not idea.exists():
        raise LintSetupError(f"{idea} not found")
    banned = parse_banned_words(idea.read_text(encoding="utf-8"))

    lineage: list[str] = []
    lin_path = root / "docs" / "private" / "lineage_terms.txt"
    if lin_path.exists():
        lineage = [
            t.strip()
            for t in lin_path.read_text(encoding="utf-8").splitlines()
            if t.strip() and not t.startswith("#")
        ]
    else:
        unverifiable.append("UNVERIFIABLE: docs/private/lineage_terms.txt missing")

    nums_path = root / "docs" / "operations" / "VIDEO_NUMBERS.md"
    if not nums_path.exists():
        nums_path = root / "docs" / "VIDEO_NUMBERS.md"
    registry = parse_numbers_registry(nums_path.read_text(encoding="utf-8")) if nums_path.exists() else {}
    if not nums_path.exists():
        v("numbers", "docs/operations/VIDEO_NUMBERS.md missing: no number can be verified")

    script = script_path.read_text(encoding="utf-8")
    beats = parse_beats(script)
    if not beats:
        v("structure", "no beats found (expected '## M:SS-M:SS [Cn]' headings)")

    # banned words + lineage terms: whole script, including headings/comments
    terms = [(w, "banned") for w in banned] + [(t, "lineage") for t in lineage]
    for ln, line in enumerate(script.splitlines(), 1):
        for term, kind in terms:
            if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", line, re.I):
                v(kind, f"{kind} term '{term}'" if kind == "banned" else "lineage term present", ln)

    # numbers
    for b in beats:
        for ln, text in b["vo"] + b["screen"]:
            if PENDING in text:
                v("numbers", f"unmeasured number placeholder {PENDING}", ln)
            for tok in NUM_RE.findall(NAME_RE.sub("", text.replace(PENDING, ""))):
                key = tok.rstrip("%")
                status = registry.get(key)
                if status is None:
                    v("numbers", f"number '{tok}' not registered in docs/VIDEO_NUMBERS.md", ln)
                elif not status.lower().startswith("measured"):
                    v("numbers", f"number '{tok}' has status '{status}', needs 'Measured'", ln)

    # concepts
    concepts = _load_concepts(concepts_path) if concepts_path.exists() else []
    if not concepts_path.exists():
        v("concepts", f"{concepts_path} missing")
    if len(concepts) > MAX_CONCEPTS:
        v("concepts", f"{len(concepts)} concepts declared; cap is {MAX_CONCEPTS}")
    declared = {str(c.get("id")) for c in concepts if isinstance(c, dict)}
    used = {c for b in beats for c in b["concepts"]}
    for cid in sorted(declared - used):
        v("concepts", f"concept {cid} maps to no script line")
    for cid in sorted(used - declared):
        v("concepts", f"script uses undeclared concept {cid}")
    if len(used) > MAX_CONCEPTS:
        v("concepts", f"script uses {len(used)} concepts; cap is {MAX_CONCEPTS}")

    # length
    vo_words = sum(len(t.split()) for b in beats for _, t in b["vo"])
    est = vo_words / WPM * 60
    if est > MAX_SECONDS:
        v("length", f"estimated VO length {est:.0f}s exceeds {MAX_SECONDS}s at {WPM} wpm")
    if beats and max(b["end"] for b in beats) > MAX_SECONDS:
        v("length", f"script timeline ends after {MAX_SECONDS}s")

    # hook
    if beats:
        first = min(beats, key=lambda b: b["start"])
        if first["start"] != 0 or not (first["vo"] or first["screen"]):
            v("hook", f"no hook: a beat starting at 0:00 with content is required (first {HOOK_SECONDS} s)")
        elif first["end"] < HOOK_SECONDS:
            v("hook", "first beat ends before the 5 s hook window closes")

    # tagline
    vo_lines = [t for b in sorted(beats, key=lambda b: b["start"]) for _, t in b["vo"]]
    if not vo_lines or vo_lines[-1].strip("*_ \"'\u201c\u201d") != TAGLINE:
        v("tagline", f"last VO line must be exactly: {TAGLINE}")

    return {
        "script": str(script_path),
        "violations": violations,
        "unverifiable": unverifiable,
        "banned_words": banned,
        "estimated_vo_seconds": round(est, 1),
        "concepts_declared": sorted(declared),
        "concepts_used": sorted(used),
        "ok": not violations and not unverifiable,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script", type=Path)
    ap.add_argument("--concepts", type=Path, default=None)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    concepts = a.concepts or (a.script.parent / "concepts.yaml")
    try:
        res = lint(a.script, concepts, a.root)
    except LintSetupError as e:
        print(f"LINT SETUP ERROR: {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for x in res["violations"]:
            loc = f":{x['line']}" if x["line"] else ""
            print(f"VIOLATION[{x['rule']}] {a.script}{loc}: {x['message']}")
        for u in res["unverifiable"]:
            print(u)
        print(f"{len(res['violations'])} violation(s); est VO {res['estimated_vo_seconds']}s; ok={res['ok']}")
    if res["violations"]:
        return 1
    return 2 if res["unverifiable"] else 0


if __name__ == "__main__":
    sys.exit(main())
