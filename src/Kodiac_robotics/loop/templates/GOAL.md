# /goal recipe (identical for every bug)

/goal Fix `{{sim_script}}` so the robot completes the task in `{{test}}`. Done ONLY when Kodiac run prints PASS.

## How to work
1. Call the MCP tool `Kodiac.verify` with `{"test": "{{test}}", "sim_script": "{{sim_script}}", "seed": {{seed}}}`.
2. Read the verdict. On FAIL, use the measured evidence in the response (failed step, decisive numbers with their
   uncertainty, and blame / hint when present) to decide what to change in `{{sim_script}}`.
3. Edit only `{{sim_script}}`. Then call `Kodiac.verify` again. Repeat.
4. Only stop when `Kodiac.verify` returns `"verdict": "PASS"`. A CAN'T TELL verdict is not a pass.

## Rules
- Do NOT edit `{{test}}`, any `.green` file, thresholds, or anything under `.Kodiac/`. The Stop-hook gate
  re-runs the pinned test against the current script itself; it does not read `.Kodiac/last_verdict.json`.
- If the gate says `GATE EXHAUSTED: goal NOT verified`, the goal has FAILED. Do not report success.
- A result badged `[MOCK SIMULATION]` came from the kinematic mock simulator, not ManiSkill physics. Say so when you report it.
