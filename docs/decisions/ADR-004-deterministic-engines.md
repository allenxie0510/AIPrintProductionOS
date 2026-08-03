# ADR-004: Deterministic Engines, Advisory AI

- Status: Accepted
- Date: 2026-08-03

## Context

LLMs are useful for explanation but are not deterministic PDF, color or image engines.

## Decision

Parsers observe, rules decide, fix engines mutate and validators verify. AI reads their outputs to explain, suggest and orchestrate human decisions.

## Consequences

- Production behavior is testable without an LLM.
- Prompts cannot override severity, thresholds or safety gates.
- AI errors cannot directly corrupt the source artifact.
