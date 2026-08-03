# AI Context

This repository is the specification and implementation source of truth for AI Print Production OS.

Before making changes, read in order:

1. `PROJECT.md`
2. `docs/00-project/constitution.md`
3. `docs/01-product/alpha-prd.md`
4. `docs/README.md`
5. Relevant ADRs under `docs/decisions/`
6. The relevant architecture, engine and test specifications.

Do not:

- Treat historical chat text as a specification.
- Treat `PROJECT_BOOTSTRAP.md` or superseded governance snapshots as current instructions.
- Expand MVP input beyond PDF without an accepted RFC.
- Put deterministic production decisions inside LLM prompts.
- Claim that resampling creates real image detail.
- Silently substitute fonts.
- Claim PDF/X compliance from metadata alone.
- Overwrite source files or hide unresolved preflight failures.
- Change architecture invariants without an ADR.

When code and docs disagree, stop and surface the inconsistency. An accepted ADR has priority over older narrative documents.

Alpha implementation is authorized when it is traceable to the accepted PRD, preserves the Constitution and includes tests. Licensing, independent PDF/X validation and production isolation remain release gates; they do not block deterministic local development.
