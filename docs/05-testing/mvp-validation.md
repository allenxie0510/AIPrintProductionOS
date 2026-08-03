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
  → execute one diagnosed repair at a time
  → generate immutable derivative
  → re-analyze and qpdf validate
  → render the actual current derivative and optional source/current slider
  → download PDF
  → immediately delete all artifact bytes
```

The same live API flow was also run with both `bleed_and_crop` and explicitly acknowledged `pdfx_candidate`. The post-fix report retained only `IMAGE.LOW_EFFECTIVE_DPI`; the 84.67 PPI issue was not hidden.

## Automated coverage

### Python — 19 passing tests

- invalid file and unknown preset rejection;
- token isolation;
- report privacy projection;
- font-substitution confirmation gate;
- exact staged fonts remove only their own substitution acknowledgement gate;
- regression coverage for the PDF/X worker `work_dir` argument that previously broke online repair;
- high-resolution image XObject replacement, insufficient-pixel rejection and post-repair Effective PPI checks;
- rendered source/current images differ after an actual image replacement;
- PDF/X quality-regression rejection preserves the previous derivative and job state;
- invalid font payload rejection;
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
- responsive upload, diagnosis, per-issue repair, completion and result states implemented.
- uploaded PDF preview and repaired-file before/after slider implemented.
- current derivative preview is shown by default after every completed mutation; comparison is an explicit secondary mode.
- exact font upload and high-resolution image replacement controls are attached to their diagnosed issue rows.
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
