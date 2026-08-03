# Preflight Rule Engine

Status: POC

## Rule Contract

```json
{
  "code": "IMAGE.LOW_EFFECTIVE_DPI",
  "severity": "FAIL",
  "page": 1,
  "message": "...",
  "evidence": {},
  "fix": {
    "mode": "super_resolution_or_replace_source",
    "safety": "review_required"
  }
}
```

## Principles

- Stable machine-readable codes; localized messages are presentation.
- Thresholds come from versioned Print Presets.
- The same UDF and preset must produce the same result.
- Scoring is secondary to individual issues and must never hide a FAIL.
- Each new rule ships with positive, negative and boundary fixtures.

## POC Rules

- `COLOR.RGB_USED`
- `FONT.NOT_EMBEDDED`
- `IMAGE.LOW_EFFECTIVE_DPI`
- `PAGE.TRIMBOX_MISSING`
- `PAGE.BLEED_INSUFFICIENT`
- `PDFX.NOT_DECLARED`

## Next Step

Move definitions and thresholds into a versioned declarative rule catalog while keeping complex evidence functions in tested code.
