# API Design Status

Status: Deferred until Alpha architecture is accepted

The API will be specified with OpenAPI after job, artifact, print-preset and audit models are accepted. Expected resource families:

- `/projects`
- `/artifacts`
- `/print-presets`
- `/preflight-jobs`
- `/fix-plans`
- `/derivatives`
- `/reports`

No endpoint should promise synchronous PDF processing. Jobs are asynchronous and expose immutable input/output artifact identities.
