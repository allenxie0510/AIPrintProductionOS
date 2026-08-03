# AI Operating Model

Status: Accepted

## AI May

- Explain issues using UDF evidence and accepted rules.
- Translate technical findings for designers and print operators.
- Recommend a fix plan and identify required user decisions.
- Compare pre/post reports and flag suspicious outcomes.
- Draft rules, tests, RFCs and review notes for human approval.

## AI May Not

- Directly edit PDF bytes or bypass fix engines.
- Invent measurements absent from parser evidence.
- Mark a failed rule as passed through explanation.
- Select a production ICC profile without a Print Preset or explicit decision.
- Approve font substitution, generative bleed or super-resolution without the configured safety gate.

## Prompt Boundary

LLM prompts are presentation/orchestration assets, not the source of production policy. Rule codes, thresholds, fix safety and validation gates remain versioned outside prompts.
