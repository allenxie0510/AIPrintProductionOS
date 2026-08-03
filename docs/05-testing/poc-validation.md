# POC Validation Record

Status: POC evidence

## Controlled Fixture

- One A4 page.
- DeviceRGB artwork.
- Helvetica and Helvetica-Bold Base-14 references without embedded programs.
- 600 x 400 px image placed at 180 x 120 mm: expected 84.67 effective DPI.
- No explicit TrimBox, BleedBox, PDF/X declaration or OutputIntent.
- Uniform blue border suitable for a safe solid-color bleed test.

## Assertions

| Assertion | Result |
|---|---|
| Six expected issue categories detected | PASS |
| Effective DPI equals 84.67 | PASS |
| TrimBox and BleedBox explicit after fix | PASS |
| Minimum bleed equals 3.0 mm | PASS |
| Output used colors are CMYK/Gray | PASS |
| Fonts have embedded programs | PASS, with substitution warning |
| PDF/X-4 declaration and OutputIntent present | PASS as candidate |
| qpdf syntax/stream check | PASS |
| Low-DPI issue remains | PASS - intentionally unresolved |

## Commands

```bash
.venv/bin/python scripts/run_poc.py
.venv/bin/python -m unittest discover -s tests -v
qpdf --check output/pdf/poc-fixed-pdfx4.pdf
```

## Evidence

- `output/poc/verification.json`
- `output/poc/input-analysis.json`
- `output/poc/final-analysis.json`
- `output/pdf/poc-fixed-pdfx4.pdf`

The candidate PDF has not passed an independent ISO PDF/X conformance validator or print-provider acceptance test.

GitHub Actions runs the same tests and end-to-end POC on Linux with an explicitly selected POC CMYK profile, then uploads the JSON, rendered preview and PDF as short-lived workflow artifacts.
