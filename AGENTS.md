# Repository Agent Guide

## Required Reading

Read `PROJECT.md`, `AI_CONTEXT.md`, `docs/00-project/constitution.md`, the accepted Alpha PRD and relevant ADRs before implementation.

## Ownership by Area

| Area | Primary responsibility | Required validation |
|---|---|---|
| `print_preflight/` | Parser, UDF, rules and fix orchestration | Unit tests + controlled PDFs |
| `scripts/` | Reproducible POC and development utilities | Fresh end-to-end run |
| `tests/` | Regression and integration coverage | Deterministic assertions |
| `docs/02-architecture/` | System boundaries and data contracts | ADR/RFC consistency |
| `docs/03-engine/` | Parser/rule/fix specifications | Code-to-spec traceability |
| `docs/05-testing/` | Evidence and acceptance gates | Independent tools where possible |
| `output/` | POC evidence only | Must be reproducible; not source input |

## Engineering Rules

- Keep parser observations separate from rule conclusions.
- Keep rule conclusions separate from fix execution.
- A fix must declare `auto`, `confirm`, or `manual` safety.
- Every diagnostic result binds immutable Print Preset, Rule Set and rule versions.
- Preserve the original and record tool versions, ICC identity and hashes.
- Use isolated processes for untrusted PDFs; do not share PyMuPDF across threads.
- Do not weaken tests to make an unsafe fix pass.
- Generated PDF/X files remain candidates until independently validated.

## Change Process

- Small implementation changes: branch -> tests -> PR.
- New rule: update rule spec, fixtures and tests in the same PR.
- Architecture boundary or new input format: RFC, then ADR, then code.
- Changed product promise: update vision/MVP documents before implementation.
- Deterministic Alpha work covered by the accepted PRD may proceed while deployment-only license and external-validator gates remain open.
