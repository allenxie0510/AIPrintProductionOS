# System Architecture

Status: Proposed for Alpha

## Components

```text
Next.js Web
    |
Production API (auth, projects, presets, jobs)
    |
Object Storage + Job Queue
    |
Isolated Python Worker
    +-- Parser adapters -> UDF + evidence
    +-- Rule Engine -> issues + score
    +-- Fix Planner -> safety decisions
    +-- Box / Color / Font / Image engines
    +-- Independent validators
    +-- Render regression
    |
Derived PDF + JSON report + audit events

AI Decision Layer consumes UDF/issues and provides explanations.
```

## Architecture Invariants

- API and UI never run CPU-heavy PDF processing inline.
- Untrusted PDFs run in isolated, resource-limited processes or containers.
- Storage is immutable by version; source and derivatives have independent hashes.
- Parser output is observation. Rules interpret observations. Fixers mutate derivatives.
- A repair is successful only after post-fix validation.
- Print Presets bind product size, bleed, target ICC, PDF/X variant and rule thresholds.

## Initial Repository Layout

```text
docs/             specifications, ADRs, RFCs and sprints
print_preflight/  current Python POC package
scripts/          reproducible POC runners
tests/            controlled regression tests
output/           checked-in POC evidence only
```

Frontend, API and production workers should be introduced only when their first implementation exists; empty architecture folders are intentionally avoided.
