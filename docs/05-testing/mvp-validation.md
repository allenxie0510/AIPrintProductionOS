# Web MVP Validation Record

- Status: PASS for local technical MVP
- Date: 2026-08-03
- Scope: Web UI + Python API + deterministic PDF engine

## Verified user journey

```text
Upload controlled PDF
  → asynchronous job analysis
  → retrieve evidence report
  → select solid-color bleed/crop repair
  → generate immutable derivative
  → re-analyze and qpdf validate
  → download PDF
  → immediately delete all artifact bytes
```

The same live API flow was also run with both `bleed_and_crop` and explicitly acknowledged `pdfx_candidate`. The post-fix report retained only `IMAGE.LOW_EFFECTIVE_DPI`; the 84.67 PPI issue was not hidden.

## Automated coverage

### Python — 11 passing tests

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

### Frontend

- TypeScript/Vinext production build: PASS.
- ESLint: PASS.
- server-rendered product smoke test: PASS.
- responsive upload, diagnosis, fix confirmation and result states implemented.

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

- application background tasks must become a durable queue;
- local filesystem must become lifecycle-managed object storage;
- PDF processing must run in isolated resource-limited containers;
- PyMuPDF/Ghostscript licensing must be resolved;
- PDF/X requires an approved independent validator;
- POC Print Presets require print-provider-reviewed ICC profiles;
- antivirus/malware scanning, account tenancy, rate limits and operational monitoring are not part of the local MVP.

## Result

The complete local MVP value chain is functional and regression-tested. Public SaaS launch remains a separate production-hardening milestone and must not be represented as completed by this record.
