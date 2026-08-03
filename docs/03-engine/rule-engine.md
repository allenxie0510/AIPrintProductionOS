# Preflight Rule Engine

Status: POC

## Rule Contract

```json
{
  "code": "IMAGE.LOW_EFFECTIVE_DPI",
  "ruleId": "IMAGE.LOW_EFFECTIVE_DPI",
  "ruleVersion": "1.1.0",
  "severity": "FAIL",
  "confidence": 1.0,
  "page": 1,
  "message": "...",
  "evidence": {},
  "fix": {
    "mode": "super_resolution_or_replace_source",
    "safety": "confirm"
  }
}
```

## Principles

- Stable machine-readable codes; localized messages are presentation.
- Thresholds come from versioned Print Presets.
- Finished physical scale comes from the immutable user-confirmed Target Geometry; PDF page points remain parser observations.
- The same UDF and preset must produce the same result.
- Fix safety uses only `auto`, `confirm` or `manual`.
- Every result records the Rule Set, all evaluated rule versions and the immutable Print Preset snapshot.
- Scoring is secondary to individual issues and must never hide a FAIL.
- Each new rule ships with positive, negative and boundary fixtures.

## POC Rules

- `COLOR.RGB_USED`
- `FONT.NOT_EMBEDDED`
- `IMAGE.LOW_EFFECTIVE_DPI`
- `PAGE.TARGET_SIZE_MISMATCH`
- `PAGE.TRIMBOX_MISSING`
- `PAGE.BLEED_INSUFFICIENT`
- `PDFX.NOT_DECLARED`

`PAGE.TARGET_SIZE_MISMATCH` compares observed TrimBox/MediaBox dimensions with the confirmed finished size. Equal proportions within 2% may be normalized with `confirm`; incompatible proportions are `manual`. When proportions are compatible, image placement millimetres and Effective PPI are calculated at the target finished scale.

## Next Step

Move remaining messages and severity policy into a versioned declarative catalog while keeping complex evidence functions in tested code. The Alpha foundation now records versioned presets, rule identities and deterministic rule executions in the output contract.
