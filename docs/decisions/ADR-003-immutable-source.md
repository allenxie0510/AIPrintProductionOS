# ADR-003: Immutable Source and Auditable Derivatives

- Status: Accepted
- Date: 2026-08-03

## Context

PDF fixes can change appearance, color, text and standards metadata. Overwriting removes rollback and evidence.

## Decision

The uploaded source is immutable. Every analysis and fix references its source hash; every output is a new version with provenance.

## Consequences

- Storage and database models are artifact/version oriented.
- Failed attempts may be retained for debugging under retention policy.
- Audit records include rule set, engine, profile, command/config and output hash.
