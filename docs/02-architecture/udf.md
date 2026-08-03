# Universal Design Format - POC Contract

Status: POC

## Purpose

UDF is a print-diagnostic contract shared by parsers, rules, fix planning, reports and AI explanations. It is not a lossless editable design model.

## Current Top-level Shape

```json
{
  "udfVersion": "0.1-poc",
  "source": {},
  "document": {
    "metadata": {},
    "pdfx": {},
    "colorSpaces": {},
    "fonts": [],
    "images": []
  },
  "pages": [],
  "limitations": []
}
```

## Required Production Additions

- `parser.name`, `parser.version`, `parser.durationMs`.
- `source.sha256`, MIME, byte size and ingestion identity.
- Object/page evidence references with confidence.
- Print Preset identity and version.
- Rule-set identity and version.
- Fix provenance: input hash, output hash, command/engine version, ICC hash.
- Normalized units with original PDF coordinate evidence.

## Contract Rules

- Preserve observations even when a fix later resolves an issue.
- Distinguish missing explicit boxes from PDF viewer defaults.
- Store effective image DPI per placement, not just embedded metadata.
- Separate `used` color evidence from low-confidence unused structural resources.
- Version schema changes; never silently reinterpret stored UDF.
