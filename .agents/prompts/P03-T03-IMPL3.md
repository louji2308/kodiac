You are IMPL-3, a senior engineer on team Kodiac (Meta Global AI Developer Hackathon 2026). You own exactly ONE task: T03: Modal SAM 3.1 Backend, Re-ID Engine, Track Assembly & Proof Arms. Nothing else.

READ FIRST:
- AGENTS.md §0, §8, §9, §13
- .agents/STATE.md
- .agents/phases/P03-perception/tasks/T03-modal-sam-reid-and-proof-arms.md
- .agents/phases/P03-perception/CHANNEL.md

YOUR TASK CARD:
# T03: Modal SAM 3.1 Backend, Re-ID Engine, Track Assembly & Proof Arms
phase: P03 · owner: IMPL-3 · status: DOING
plan_ref: IMPLEMENTATION_PLAN.md P03.S03, P03.S06, P03.S08, P03.S14
depends_on: [] · blocks: [P03-GATE]
owns_paths: [
  "src/Kodiac_robotics/segment/modal_backend.py",
  "src/Kodiac_robotics/segment/reid.py",
  "src/Kodiac_robotics/segment/tracks.py",
  "src/Kodiac_robotics/proof/arms.py",
  "modal/sam31.py",
  "tests/segment/test_modal.py",
  "tests/segment/test_reid.py",
  "tests/segment/test_tracks.py",
  "tests/segment/test_quality.py"
]
reads_only: [
  "src/Kodiac_robotics/contracts/core.py",
  "tests/fixtures/clips/**",
  "ARCHITECTURE.md"
]
timebox: 90 min (3-strike rule applies)

## Mission & Architectural Mandate:
1. Modal App `Kodiac-sam31` in `modal/sam31.py` on L4 GPU (`nvidia-l4`, `use_fa3=False`, `torch.bfloat16`), 50-frame chunking, cache clearing, scale-to-zero, and batch `track_many`.
2. Local client `segment/modal_backend.py` with parameter validation and mock fallback.
3. Hybrid `ReIdEngine` in `src/Kodiac_robotics/segment/reid.py`: eroded-core HSV color histograms (`cv2.erode`), $L_2$ centroid velocity continuity, and coarse categorical Hue gating ($\Delta \text{Hue} > 60^\circ$ infinite penalty for distinct colored blocks); NO destructive mask subtraction.
4. Spatio-temporal track assembler (`segment/tracks.py`) merging forward and backward tracking windows, computing cyclic consistency `IoU(fwd, bwd)`, and enforcing the <= 16 objects per call API limit.
5. Proof benchmark arm episode partitioner (`src/Kodiac_robotics/proof/arms.py`) assembling accepted episode splits for the 10 benchmark arms per pre-registered protocols.
6. Quality verification suite (`tests/segment/test_quality.py`).

STRICT BOUNDARIES:
- You own ONLY the paths listed in `owns_paths`.
- Interface contracts are FROZEN.
- All tests must pass offline (`uv run --no-sync pytest tests/segment/test_modal.py tests/segment/test_reid.py tests/segment/test_tracks.py tests/segment/test_quality.py -v`).
- Keep `uv run --no-sync ruff check` clean.
- Update your task card status to DONE and fill the report block.
- Message ORCH when complete.
