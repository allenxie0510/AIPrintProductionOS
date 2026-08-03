# AI Context

This repository is the specification and implementation source of truth for AI Print Production OS.

Before making changes, read in order:

1. `PROJECT.md`
2. `docs/00-project/constitution.md`
3. `docs/README.md`
4. Relevant ADRs under `docs/decisions/`
5. The current sprint under `docs/06-sprints/`

Do not:

- Treat historical chat text as a specification.
- Expand MVP input beyond PDF without an accepted RFC.
- Put deterministic production decisions inside LLM prompts.
- Claim that resampling creates real image detail.
- Silently substitute fonts.
- Claim PDF/X compliance from metadata alone.
- Overwrite source files or hide unresolved preflight failures.
- Change architecture invariants without an ADR.

When code and docs disagree, stop and surface the inconsistency. An accepted ADR has priority over older narrative documents.
