# PDF-first MVP Scope

Status: Accepted

## Users

- Designers and operators who can export PDF but are not prepress experts.
- Print providers who need consistent, explainable intake decisions.
- Internal prepress teams who need faster triage and auditable fixes.

## Core Workflow

1. Upload PDF and select product/print preset.
2. Parse to UDF with evidence and confidence.
3. Run versioned rules.
4. Show PASS/WARN/FAIL and production score.
5. Build a fix plan: auto, confirm or manual.
6. Execute selected fixes on a derivative.
7. Re-parse, validate and render-compare.
8. Export PDF and audit report.

## MVP Checks

- Page count, size, rotation and boxes.
- Effective image DPI.
- Font references and embedding state.
- RGB/CMYK/Gray plus basic spot/transparency signals.
- Trim/Bleed requirements.
- PDF/X declaration and OutputIntent evidence.

## MVP Fixes

- Confirmed TrimBox/BleedBox and crop marks.
- Uniform solid-color bleed extension.
- Print-preset-driven ICC conversion.
- Exact font embedding when available and permitted.
- PDF/X candidate generation followed by independent validation.

## Explicit Exclusions

- Source design reconstruction.
- Silent font substitution.
- Automatic acceptance of AI-generated image detail.
- Universal bleed generation.
- A generic CMYK profile presented as production-ready.
