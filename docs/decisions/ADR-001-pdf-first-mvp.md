# ADR-001: PDF-first MVP

- Status: Accepted
- Date: 2026-08-03

## Context

Figma, Canva, HTML and other source formats have incompatible semantics, while almost all target workflows can export PDF.

## Decision

The first product accepts PDF and optimizes PDF preflight reliability. Non-PDF semantic reconstruction requires a separate RFC.

## Consequences

- The parser contract is print-diagnostic, not an editable source model.
- Engineering effort goes into rules, presets, fixes and validation.
- Source-tool integrations may later improve export guidance without blocking MVP.
