# MVP API

- Status: Implemented
- Base path: `/v1`
- Interactive OpenAPI: `/docs` on the Python API service

## Authentication model

The anonymous MVP returns a high-entropy `accessToken` when a job is created. Every later job request requires the token in `X-Job-Token`. Only its SHA-256 hash is stored.

This protects unguessable task URLs but is not an account system. Tenant accounts, signed object-store uploads and rate limiting remain production hardening work.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service health |
| `GET` | `/v1/presets` | Versioned POC Print Presets |
| `POST` | `/v1/jobs` | Stream a PDF into an ephemeral job and enqueue analysis |
| `GET` | `/v1/jobs/{jobId}` | Job state, score and expiry |
| `GET` | `/v1/jobs/{jobId}/report` | Evidence, issues and validation report |
| `POST` | `/v1/jobs/{jobId}/fix` | Execute confirmed safe fix plan |
| `GET` | `/v1/jobs/{jobId}/download` | Download the current candidate PDF |
| `DELETE` | `/v1/jobs/{jobId}/artifacts` | Immediately delete source/intermediate/output bytes |
| `POST` | `/v1/jobs/{jobId}/feedback` | Record rule/fix and printer outcome feedback |

## Current fix actions

- `bleed_and_crop`: executes only when the border classifier permits deterministic solid-color extension.
- `pdfx_candidate`: ICC conversion and PDF/X-4 candidate generation. Missing fonts require explicit substitution acknowledgement. It never returns independent PDF/X certification.

## State model

`queued → analyzing → awaiting_decision → fixing → validating → ready | partial | failed → deleted`

The current MVP uses an application background task. Production deployment replaces that executor with a durable queue while preserving the API and job contracts.

## File lifecycle

Files default to a 24-hour TTL and can be deleted immediately. `scripts/cleanup_jobs.py` is the reconciliation command for cron or a scheduled job. Durable SQLite rows contain only technical metadata, reports, decisions and feedback; source and output paths become unusable after deletion.
