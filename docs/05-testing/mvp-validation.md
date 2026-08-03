# Web MVP Validation Record

- Status: PASS for local technical MVP
- Date: 2026-08-03
- Scope: Web UI + Python API + deterministic PDF engine

## Verified user journey

```text
Upload controlled PDF
  → asynchronous job analysis
  → render token-protected source preview
  → retrieve evidence report
  → select solid-color bleed/crop repair
  → generate immutable derivative
  → re-analyze and qpdf validate
  → render source/current before-after comparison
  → download PDF
  → immediately delete all artifact bytes
```

The same live API flow was also run with both `bleed_and_crop` and explicitly acknowledged `pdfx_candidate`. The post-fix report retained only `IMAGE.LOW_EFFECTIVE_DPI`; the 84.67 PPI issue was not hidden.

## Automated coverage

### Python — 14 passing tests

- invalid file and unknown preset rejection;
- token isolation;
- report privacy projection;
- font-substitution confirmation gate;
- upload/report/fix/download/delete integration;
- privacy-safe metadata retention after delete;
- controlled POC analysis and PDF/X generation;
- Print Preset and Rule Set versioning;
- runtime override identity;
- invalid preset validation.
- bounded edge sampling for a generated 5280 × 7500 pt large-format page.
- bounded PNG preview rendering and authenticated source/current preview endpoints;
- complex-border rejection for automatic bleed plus honest trim/crop fallback;
- confirmation that trim-only repair leaves the insufficient-bleed issue unresolved.

### Resource regression

- image placements are extracted from content streams without decoding image pixels;
- page-edge classification renders four narrow clips instead of the full page;
- the previously failing large-format analysis path fell from approximately 1.4 GB peak memory to approximately 85 MB locally;
- analyze and fix stages execute in isolated subprocesses with memory, CPU and wall-time limits in the deployed container.

### Frontend

- TypeScript/Vinext production build: PASS.
- ESLint: PASS.
- server-rendered product smoke test: PASS.
- responsive upload, diagnosis, fix confirmation and result states implemented.
- uploaded PDF preview and repaired-file before/after slider implemented.
- unavailable repair actions are disabled from the server-authored executable plan.
- transient Render 502/503/504 polling failures retry with bounded exponential backoff and actionable Chinese errors.

### Independent structure check

- qpdf syntax/stream check on the live downloaded derivative: PASS.

## Security and privacy checks

- uploaded bytes are streamed with a hard size limit;
- PDF signature and page limit are checked;
- source filenames are reduced to a basename;
- source/output paths and engine commands are removed from public reports;
- job access tokens are stored only as SHA-256 hashes;
- immediate deletion removes the job directory and clears stored paths;
- durable report is reduced to a privacy-safe production summary after deletion;
- expired artifact cleanup is available as a scheduled command.

## Honest limitations

This validation does not prove public production readiness. Remaining gates:

- application background tasks must become a durable queue; the demo now isolates engine processes but queue state is still local;
- local filesystem must become lifecycle-managed object storage;
- PDF processing must move from resource-limited subprocesses to isolated worker containers for production;
- PyMuPDF/Ghostscript licensing must be resolved;
- PDF/X requires an approved independent validator;
- POC Print Presets require print-provider-reviewed ICC profiles;
- antivirus/malware scanning, account tenancy, rate limits and operational monitoring are not part of the local MVP.

## Result

The complete local MVP value chain is functional and regression-tested. Public SaaS launch remains a separate production-hardening milestone and must not be represented as completed by this record.
