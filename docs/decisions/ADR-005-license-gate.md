# ADR-005: Licensing Is an Alpha Gate

- Status: Accepted
- Date: 2026-08-03

## Context

The POC uses PyMuPDF/MuPDF and Ghostscript. Both have AGPL/commercial licensing implications for a closed-source SaaS.

## Decision

Before Alpha deployment, choose and document one path: commercial Artifex license, an approved replacement stack, or an AGPL-compliant product model reviewed by counsel.

## Consequences

- POC code is valid for technical evaluation but does not decide production licensing.
- Engine abstraction boundaries remain explicit.
- Procurement/legal work is tracked alongside architecture, not postponed to launch.
