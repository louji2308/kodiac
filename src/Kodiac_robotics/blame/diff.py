"""Event diff: demo events (from `.green.lock`) vs attempt events. ARCHITECTURE.md sections 5.4, 9.

Alignment is Myers LCS on `(step, kind, predicate)`. A matched pair whose shared measurements all
agree within `sigma_k` x combined sigma prints as a context line (two spaces); a matched pair that
diverges, a demo-only event and an attempt-only event print as `-` / `+` lines. Measurements print
as `name value +/- sigma unit`.

Direction words: signed `dx`/`dy`/`dz` measurements (key containing `dx`, `dy` or `dz` as a token)
print as `camera-right/left` (dx), `camera-up/down` (dy), `toward/away from camera` (dz), because
only Tier A has metric world axes; Tier A prints `+x/-x`, `+y/-y`, `+z/-z`. Convention: +dx is
image-right, +dy is image-up, +dz is toward the camera.
"""

from __future__ import annotations

import math
import re
from typing import Literal, Sequence, TypeVar

from Kodiac_robotics.contracts.core import Event

T = TypeVar("T")

_UNIT_BY_SUFFIX = {
    "align_xy": "cm",
    "gap": "cm",
    "height": "cm",
    "slip": "cm",
    "distance": "cm",
    "rim_margin": "cm",
    "front_occluder": "cm",
    "speed": "cm/s",
    "duration": "s",
    "scale_ratio": "ratio",
    "depth_consistency": "ratio",
}
_DIR_TOKEN = re.compile(r"(?:^|[._])(dx|dy|dz)(?:[._]|$)")
_DIR_WORDS = {
    "dx": ("camera-right", "camera-left"),
    "dy": ("camera-up", "camera-down"),
    "dz": ("toward camera", "away from camera"),
}
_WORLD_WORDS = {"dx": ("+x", "-x"), "dy": ("+y", "-y"), "dz": ("+z", "-z")}


def myers_lcs(a: Sequence[T], b: Sequence[T]) -> list[tuple[int | None, int | None]]:
    """Myers O(ND) shortest edit script as aligned index pairs.

    `(i, j)` is a match, `(i, None)` a deletion from `a`, `(None, j)` an insertion from `b`.
    Within a run of edits deletions precede insertions; the pairs cover every index exactly once.
    """
    n, m = len(a), len(b)
    if n == 0 and m == 0:
        return []
    max_d = n + m
    offset = max_d
    v = [0] * (2 * max_d + 2)
    trace: list[list[int]] = []
    found_d = 0
    for d in range(max_d + 1):
        trace.append(v[:])
        done = False
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v[offset + k - 1] < v[offset + k + 1]):
                x = v[offset + k + 1]
            else:
                x = v[offset + k - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v[offset + k] = x
            if x >= n and y >= m:
                done = True
                break
        if done:
            found_d = d
            break

    pairs: list[tuple[int | None, int | None]] = []
    x, y = n, m
    for d in range(found_d, 0, -1):
        vd = trace[d]
        k = x - y
        if k == -d or (k != d and vd[offset + k - 1] < vd[offset + k + 1]):
            prev_k = k + 1
        else:
            prev_k = k - 1
        prev_x = vd[offset + prev_k]
        prev_y = prev_x - prev_k
        while x > prev_x and y > prev_y:
            x -= 1
            y -= 1
            pairs.append((x, y))
        if x == prev_x:
            y -= 1
            pairs.append((None, y))
        else:
            x -= 1
            pairs.append((x, None))
    while x > 0 and y > 0:
        x -= 1
        y -= 1
        pairs.append((x, y))
    pairs.reverse()
    return _deletions_first(pairs)


def _deletions_first(
    pairs: list[tuple[int | None, int | None]],
) -> list[tuple[int | None, int | None]]:
    """Within each run of non-matches, list deletions before insertions (diff convention)."""
    out: list[tuple[int | None, int | None]] = []
    run: list[tuple[int | None, int | None]] = []
    for p in pairs + [(0, 0)]:
        if p[0] is None or p[1] is None:
            run.append(p)
            continue
        out.extend(sorted(run, key=lambda q: q[0] is None))  # stable: deletions first
        run = []
        out.append(p)
    out.pop()  # sentinel
    return out


def _unit(key: str) -> str:
    if _DIR_TOKEN.search(key):
        return "cm"
    suffix = key.rsplit(".", 1)[-1]
    if suffix in _UNIT_BY_SUFFIX:
        return _UNIT_BY_SUFFIX[suffix]
    if key.endswith("_cm"):
        return "cm"
    if key.endswith("_s"):
        return "s"
    return ""


def _fmt_measurement(key: str, value: float, sigma: float, tier: str) -> str:
    unit = _unit(key)
    digits = 2 if unit in ("s", "ratio", "") else 1
    direction = ""
    token = _DIR_TOKEN.search(key)
    shown = value
    if token is not None:
        positive, negative = (_WORLD_WORDS if tier == "A" else _DIR_WORDS)[token.group(1)]
        if abs(value) > sigma:  # a sign inside the noise carries no direction
            direction = " " + (positive if value >= 0 else negative)
        shown = abs(value)
    text = f"{key} {shown:.{digits}f} \u00b1 {sigma:.{digits}f}"
    if unit:
        text += f" {unit}"
    return text + direction


def _describe(e: Event, tier: str, demo_t_s: float | None = None) -> str:
    pred = f" {e.predicate}({', '.join(e.args)})" if e.predicate else ""
    head = f"[{e.step}] {e.step_name}: {e.kind}{pred} @ {e.t_s:.2f} s"
    if demo_t_s is not None:
        head += f" (demo {demo_t_s:.2f} s)"
    else:
        head += f" (frame {e.frame})"
    if e.measurements:
        head += "; " + "; ".join(
            _fmt_measurement(k, v[0], v[1], tier) for k, v in e.measurements.items()
        )
    return head


def _diverging(demo: Event, att: Event, sigma_k: float) -> list[str]:
    bad = []
    for key in demo.measurements.keys() & att.measurements.keys():
        (dv, ds), (av, a_s) = demo.measurements[key], att.measurements[key]
        if abs(av - dv) > sigma_k * math.hypot(ds, a_s):
            bad.append(key)
    return sorted(bad)


def _key(e: Event) -> tuple[int, str, str | None]:
    return (e.step, e.kind, e.predicate)


def diff_events(
    demo: list[Event],
    attempt: list[Event],
    *,
    camera_tier: Literal["A", "B", "C"] = "C",
    sigma_k: float = 2.0,
) -> str:
    """Unified-diff style text of demo vs attempt events with measurements."""
    pairs = myers_lcs([_key(e) for e in demo], [_key(e) for e in attempt])
    body: list[str] = []
    n_ctx = n_del = n_add = 0
    for i, j in pairs:
        if i is not None and j is not None:
            d, a = demo[i], attempt[j]
            bad = _diverging(d, a, sigma_k)
            if bad:
                body.append(f"- {_describe(d, camera_tier)}")
                body.append(f"+ {_describe(a, camera_tier)}")
                body.append(f"  ^ outside {sigma_k:g} sigma: {', '.join(bad)}")
                n_del += 1
                n_add += 1
            else:
                body.append(f"  {_describe(a, camera_tier, demo_t_s=d.t_s)}")
                n_ctx += 1
        elif i is not None:
            body.append(f"- {_describe(demo[i], camera_tier)}")
            n_del += 1
        elif j is not None:
            body.append(f"+ {_describe(attempt[j], camera_tier)}")
            n_add += 1
    header = [
        "--- demo",
        "+++ attempt",
        f"@@ {n_ctx} matched, {n_del} demo-only/diverging, {n_add} attempt-only/diverging "
        f"(tier {camera_tier}; {'world axes' if camera_tier == 'A' else 'camera-relative directions'}) @@",
    ]
    return "\n".join(header + body) + "\n"
