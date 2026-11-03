# ATTRIBUTIONS.md

| Component | License | Origin / Project | Usage in Kodiac |
|---|---|---|---|
| Meta Model API / SAM 3.1 | Meta Commercial / Evaluation Terms | Meta AI | Object tracking, segmentation, backward frame inspection |
| Muse Spark 1.3 / Wonder 1.0 / Voice | Meta Commercial / Evaluation Terms | Meta AI | Test compilation, visual crop judging, ASR transcription |
| LeRobot | Apache-2.0 | Hugging Face | Dataset loaders and baseline rewards |
| ManiSkill3 | Apache-2.0 | SAPIEN / ManiSkill | StackCube-v1 environment and motion planning baseline |
| supervision | MIT | Roboflow | Mask and bounding box annotations |
| rerun-sdk | Apache-2.0 / MIT | Rerun.io | Spatial-temporal timeline visualizer |
| DROID dataset | Unverified here (upstream states CC BY 4.0; no independent verification) | Stanford / UC Berkeley / TRI, droid-dataset.github.io | Read-only `lerobot://` ingest path for real-robot clips. **No DROID data is redistributed in this repository**: the appearance experiment points at local paths that do not exist. Confirm the licence at the upstream URL before shipping any episode. |
| Robometer-4B / TOPReward | Unverified here (not downloaded) | Named baseline judge arms from the public Robometer / TOPReward work | **Named only** as comparison baselines in the pre-registered protocol and chart legends. No weights were fetched, no code is vendored, and neither arm produced a number (both are absent with a reason when no judge labels exist). |
| Hugging Face cookbook | Unverified here (upstream declares MIT); nothing copied | Hugging Face | Reference for dataset / reward-model usage patterns. No source is vendored; if any snippet is later copied, record its licence here first. |
| typer / rich | MIT | Tiangolo / Textualize | CLI interface and rich terminal outputs |
| pydantic / lark | MIT | Pydantic / Lark-parser | Data contracts and DSL grammar compiler |

Everything in the last two columns is a statement about *this repository*, not about the upstream
projects. Where the licence says "Unverified", Kodiac claims nothing: the compliance checker
(`scripts/compliance_check.py`) requires a row per component so the question is recorded, not answered
by guesswork. AGENTS.md 12.7 makes an unclear licence a human decision; `HUMAN_TODO.md` carries the list.
