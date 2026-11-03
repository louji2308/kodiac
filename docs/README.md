# Kodiac Documentation

This directory contains the organized documentation and governance files for the Kodiac project.

## Directory Structure

```text
docs/
├── features.yaml                  # Ground-truth tracked feature registry (F01–F60)
├── architecture/                  # Architectural specs, invariants, and designs
│   ├── IDEA.md                   # Concept invariants, 3 verbs, and core product specification
│   ├── ARCHITECTURE.md           # System components, interface contracts, and data flow
│   ├── DESIGN.md                 # Mathematical models, uncertainty gating, and predicate logic
│   └── TOOLS_AND_REQUIREMENTS.md # Tool selection, dependency constraints, and compute budgets
├── planning/                      # Project execution, phases, and task tracking
│   ├── IMPLEMENTATION_PLAN.md    # Multi-phase execution plan and exit gates
│   ├── BUILD_LOG.md              # Dated build milestone and commit log
│   └── TODO.md                   # Active task tracker and blocker resolution checklist
├── operations/                    # Deployment, runbooks, and submission materials
│   ├── OPS_RUNBOOK.md            # Operation commands, local demo, and server deployment
│   ├── DEMO_FILMING_GUIDE.md     # Video recording constraints, angles, and hero object rules
│   ├── SUBMISSION.md             # Hackathon submission manifest, portal copy, and form fields
│   └── VIDEO_NUMBERS.md          # Audited claims and measured metrics registry
├── governance/                    # Hackathon compliance, licensing, and legal disclosures
│   ├── HACKATHON.md              # Hackathon rules, criteria, and disqualifier safeguards
│   ├── ATTRIBUTIONS.md           # Third-party licenses and open source attributions
│   └── HUMAN_TODO.md             # Human-only sign-offs and sensitive checklist items
└── research/                      # Scientific protocols and experiment pre-registration
    └── PREREGISTRATION.md        # Pre-registered experimental protocols and hypotheses
```

## Ground Truth
- Ground truth for shipped feature statuses is maintained in [`features.yaml`](features.yaml).
- Run `python scripts/gen_status_table.py --check` to verify that the status table in `README.md` is synchronized with `features.yaml`.
