# Knowledge Graph: Issue -> Rule -> Fix -> Validation

Status: Proposed

The project knowledge model links evidence to executable behavior:

```text
PrintPreset
    -> RuleDefinition
        -> IssueInstance
            -> Evidence (page/object/measurement)
            -> FixCapability
                -> FixPlan (auto/confirm/manual)
                    -> DerivativeArtifact
                        -> ValidationResult
                            -> Rule re-check
                            -> Structure check
                            -> Render comparison
                            -> Human approval
```

## Example Mapping

| Issue | Rule | Fix | Validation |
|---|---|---|---|
| `COLOR.RGB_USED` | Target preset forbids RGB | ICC conversion | No used RGB + OutputIntent + proof/review |
| `FONT.NOT_EMBEDDED` | All production fonts embedded | Exact embed or confirm substitute | Font program + identity + render diff |
| `IMAGE.LOW_EFFECTIVE_DPI` | Placement DPI below threshold | Identify by protected thumbnail, then replace or enhance | Original fact retained + output QA |
| `PAGE.BLEED_INSUFFICIENT` | Minimum 3 mm | Solid extend / confirmed edge-pixel mirror / manual | One TrimBox, explicit BleedBox + edge coverage + preview |

Stable IDs make it possible to trace a UI explanation, report row, fix implementation and regression fixture back to the same production rule.
