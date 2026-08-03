# Sprint 1 — Alpha Deterministic Foundation

- Status: Completed for MVP foundation
- PRD: [`Online PDF Preflight Alpha PRD`](../01-product/alpha-prd.md)
- Technical design: [`Alpha Technical Design`](../02-architecture/alpha-technical-design.md)

## Goal

Turn the POC result into stable, versioned domain contracts before introducing distributed upload and worker infrastructure.

## Scope

- [x] Accept Alpha PRD and consolidate governance.
- [x] Add immutable versioned Print Presets with explicit POC status.
- [x] Bind every preflight result to a Print Preset and Rule Set.
- [x] Add rule identity/version, confidence and normalized fix safety.
- [x] Emit an execution record for every evaluated core rule.
- [x] Add CLI preset selection.
- [x] Add unit and end-to-end regression coverage.
- [x] Define API-validated FixPlan, Job and feedback schemas.
- [x] Add a local Job state machine and integration tests.
- [ ] Introduce parser/fixer/validator adapter protocols (production-hardening follow-up).

## Acceptance Criteria

- The controlled fixture still reports 84.67 effective PPI and remains FAIL under 120/150/300 PPI presets.
- Every issue has `ruleId`, `ruleVersion`, confidence and `auto|confirm|manual` safety.
- Every rule run records the exact preset snapshot and all evaluated rule versions.
- Runtime threshold overrides cannot retain the original preset identity/version.
- Existing POC repair and validation tests remain green.
- No output claims independent PDF/X compliance.

## Exit Gate

The deterministic MVP foundation is complete. Vendor-neutral parser/fixer/validator protocols remain required before replacing the POC engines or deploying a closed-source production worker.
