# Sprint 0 - Foundation and POC

Status: In review

## Goal

Turn the initial product/architecture discussion into a repository source of truth and preserve a reproducible PDF Preflight POC.

## Completed

- Controlled sample generator.
- PDF -> UDF 0.1 parser.
- Six-rule preflight engine and score.
- Safe solid-color bleed and crop marks.
- CMYK/font/PDF-X candidate path.
- qpdf, Poppler and visual verification evidence.
- Unit and Ghostscript integration tests.
- Project memory, architecture, engine specs and ADR set.

## Exit Criteria

- [x] POC runs from a clean Python environment with documented system dependencies.
- [x] Tests pass without warnings from project code.
- [x] Feasibility report records positive and negative findings.
- [x] Architecture decisions prevent silent font replacement and source overwrite.
- [ ] Independent PDF/X validator selected.
- [ ] Artifex license or replacement-engine decision approved.
- [ ] Two Alpha Print Presets selected with print-provider input.

Unchecked items are gates for Alpha, not reasons to rewrite the POC result.
