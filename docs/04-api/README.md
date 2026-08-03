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
| `POST` | `/v1/jobs` | Stream a PDF into an ephemeral job, bind Print Preset plus confirmed Trim Size and enqueue analysis |
| `GET` | `/v1/jobs/{jobId}` | Job state, score and expiry |
| `GET` | `/v1/jobs/{jobId}/report` | Evidence, issues and validation report |
| `GET` | `/v1/jobs/{jobId}/preview?stage=source|current&page=1` | Token-protected, no-store PNG preview |
| `GET` | `/v1/jobs/{jobId}/assets/image-thumbnail?xref=…` | Token-protected, no-store thumbnail for one diagnosed image object |
| `POST` | `/v1/jobs/{jobId}/fix` | Execute confirmed safe fix plan |
| `POST` | `/v1/jobs/{jobId}/assets/image-replacement` | Replace one diagnosed image XObject with a sufficient high-resolution original |
| `POST` | `/v1/jobs/{jobId}/assets/font` | Validate and stage an exact TTF/OTF font for candidate export |
| `GET` | `/v1/jobs/{jobId}/download` | Download the current candidate PDF |
| `DELETE` | `/v1/jobs/{jobId}/artifacts` | Immediately delete source/intermediate/output bytes |
| `POST` | `/v1/jobs/{jobId}/feedback` | Record rule/fix and printer outcome feedback |

## Current fix actions

- `bleed_and_crop`: uses automatic solid-color extension for uniform edges or confirmed non-generative edge-pixel mirror extension for complex image edges. It normalizes from TrimBox, writes exactly 3/5 mm according to the preset and produces one top-painted vector Registration crop-mark set outside BleedBox.
- `trim_and_crop_marks`: adds a slug, explicit TrimBox and top-painted vector Registration crop marks without generating or declaring bleed. This is the honest fallback for complex page borders.

Both geometry actions report `cropMarksVector=true`, `cropMarksColorSpace=Separation/All` and `cropMarksPaintOrder=topmost`. The `/All` tint transform maps to 100% on every C/M/Y/K process plate and is explicitly preserved by the PDF/X candidate conversion.
- `pdfx_candidate`: one document-wide ICC conversion across every page plus PDF/X-4 candidate generation. Missing fonts require explicit substitution acknowledgement. It never returns independent PDF/X certification.

`POST /v1/jobs` requires `presetId`, `sizeId`, `trimWidthMm` and `trimHeightMm`. Known A/B paper IDs are validated against canonical dimensions in either orientation; `custom` accepts 10–5000 mm per edge. The immutable `targetGeometry` is returned by the job and copied into preflight policy with per-page observed size, scale and aspect-ratio compatibility.

`PAGE.TARGET_SIZE_MISMATCH` is repairable only when observed and target aspect ratios differ by at most 2%. The existing `trim_and_crop_marks` action then proportionally normalizes the complete page to the confirmed Trim Size. A larger ratio mismatch makes geometry and bleed actions non-executable.

`image-replacement` accepts `xref` plus PNG/JPEG/TIFF/WebP multipart data. The service calculates minimum pixel dimensions from every current placement and the active Print Preset, rejects undersized assets, preserves layout, then re-analyzes effective PPI.

`font` accepts `expectedName` plus one TTF/OTF file. Validation runs in an isolated process and compares the internal font name after removing PDF subset prefixes. Exact staged fonts remove the substitution acknowledgement for that font; nonmatching fonts are rejected and are never silently used.

The report includes `fixPlan[]` entries with `applicable`, `executable`, `safety` and `reason`. The API independently re-evaluates this plan before every mutation and returns `FIX_ACTION_UNSAFE` for a stale or unsafe client selection.

Preview and image-thumbnail PNGs are bounded renders produced in the isolated PDF worker. They use the same task token as the report, return `Cache-Control: private, no-store`, expire with the job and are deleted with all other artifacts.

## State model

`queued → analyzing → awaiting_decision → fixing → validating → ready | partial | failed → deleted`

The UI invokes one mutation at a time. After each fix, the returned report includes the updated `afterAnalysis`, `afterPreflight`, action-scoped `fix.resolvedIssues`, `fix.history`, a short `fix.summary`, and a newly rendered `current` preview. Object-number churn from a PDF rewrite is not resolution evidence for unrelated issues.

The current MVP uses an application background task. Production deployment replaces that executor with a durable queue while preserving the API and job contracts.

## File lifecycle

Files default to a 24-hour TTL and can be deleted immediately. `scripts/cleanup_jobs.py` is the reconciliation command for cron or a scheduled job. Durable SQLite rows contain only technical metadata, reports, decisions and feedback; source and output paths become unusable after deletion.
