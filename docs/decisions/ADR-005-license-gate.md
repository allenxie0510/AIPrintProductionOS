# ADR-005: Licensing Is an Alpha Gate

- Status: Accepted
- Date: 2026-08-03

## Context

The POC uses PyMuPDF/MuPDF and Ghostscript. Both have AGPL/commercial licensing implications for a closed-source SaaS.

## Decision

Before Alpha deployment, choose and document one path: commercial Artifex license, an approved replacement stack, or an AGPL-compliant product model reviewed by counsel.

For the public online evaluation, the repository owner selected the AGPL path on 2026-08-03: the repository is public, the application is licensed `AGPL-3.0-only`, material third-party licenses are disclosed, and the deployed UI links to the corresponding public source. This resolves the engineering gate for a public evaluation deployment, not the legal review or proprietary/commercial release gate.

## Consequences

- POC code is valid for technical evaluation but does not decide production licensing.
- Engine abstraction boundaries remain explicit.
- Procurement/legal work is tracked alongside architecture, not postponed to launch.
- Returning the server implementation to a private/closed-source model requires a commercial license or an accepted replacement-engine ADR before deployment.
