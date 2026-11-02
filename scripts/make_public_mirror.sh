#!/usr/bin/env bash
# Build a filtered PUBLIC MIRROR of the private working repo. Never pushes: it only PRINTS the push command.
# Making the repo public is a human action (AGENTS.md section 12.3).
#
# Usage: scripts/make_public_mirror.sh [--run] [--src DIR] [--out DIR] [--python PY]
#   default is --dry-run: prints the plan and checks prerequisites, changes nothing.
# Exit: 0 ok · 1 lint failed · 2 usage/other error · 3 git-filter-repo missing
set -euo pipefail

RUN=0
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT=""
PY="python"
while [ $# -gt 0 ]; do
  case "$1" in
    --run) RUN=1 ;;
    --dry-run) RUN=0 ;;
    --src) SRC="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    --python) PY="$2"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done
OUT="${OUT:-${SRC}/../kodiac-public-mirror}"

STRIP=(HACKATHON.md docs/research/ docs/private/ .agents/ HUMAN_TODO.md)
FILTER=(git filter-repo --invert-paths)
for p in "${STRIP[@]}"; do FILTER+=(--path "$p"); done

if ! git filter-repo --version >/dev/null 2>&1; then
  echo "git-filter-repo is not installed." >&2
  echo "Install: pip install git-filter-repo   (or see https://github.com/newren/git-filter-repo)" >&2
  exit 3
fi

echo "source : $SRC"
echo "mirror : $OUT"
echo "plan   : git clone --no-local SRC OUT; ${FILTER[*]}; lint_public.py --history"
if [ "$RUN" -eq 0 ]; then
  echo "DRY RUN: nothing was cloned or modified. Re-run with --run to build the mirror."
  exit 0
fi

if [ -e "$OUT" ]; then echo "refusing to overwrite existing $OUT" >&2; exit 2; fi
git clone --no-local "$SRC" "$OUT"
(cd "$OUT" && "${FILTER[@]}")

LINEAGE="$SRC/docs/private/lineage_terms.txt"
LINT=("$PY" "$SRC/scripts/lint_public.py" --repo "$OUT" --history)
[ -f "$LINEAGE" ] && LINT+=(--lineage-file "$LINEAGE")
if ! "${LINT[@]}"; then
  echo "LINT FAILED (or lineage list unverifiable): the mirror is NOT safe to publish." >&2
  exit 1
fi

echo
echo "Mirror lint passed. The human may publish with (NOT executed by this script):"
echo "  git -C \"$OUT\" remote add origin <PUBLIC_REPO_URL> && git -C \"$OUT\" push -u origin --all && git -C \"$OUT\" push origin --tags"
