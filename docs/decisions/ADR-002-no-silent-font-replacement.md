# ADR-002: No Silent Font Replacement

- Status: Accepted
- Date: 2026-08-03

## Context

The POC embedded fonts successfully only by substituting Helvetica with NimbusSans. A technical embedding check can pass while glyph metrics or brand fidelity change.

## Decision

Missing fonts are never silently substituted. Exact-font embedding requires identity, permission and render regression. Substitution requires preview and explicit confirmation; otherwise the issue remains unresolved.

## Consequences

- Font availability and licensing become part of the fix plan.
- Reports distinguish exact embedding, subset embedding, substitution and outline conversion.
- A post-fix `embedded=true` is insufficient evidence by itself.
