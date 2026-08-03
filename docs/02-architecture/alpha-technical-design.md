# Alpha Technical Design

- Version: 0.1.0
- Status: Accepted for incremental implementation
- Date: 2026-08-03
- Product contract: [`Alpha PRD`](../01-product/alpha-prd.md)

## 1. Purpose

This design turns the PDF Preflight POC into a production-oriented task pipeline without prematurely coupling the domain model to a web framework, queue vendor, object store or PDF SDK.

The first implementation increment is the deterministic core: versioned Print Presets, Rule Sets, issues and rule executions. Web upload and distributed processing follow behind the same contracts.

## 2. System Boundary

```text
Browser
  ├── local eligibility checks and preview
  ├── signed upload
  └── report / approval / download UI
        ↓
Production API
  ├── authentication and quotas
  ├── signed object-store URLs
  ├── jobs and decisions
  └── report projection
        ↓
Queue / Orchestrator
        ↓
Isolated Python Worker
  ├── ParserAdapter
  ├── RuleEngine
  ├── FixPlanner
  ├── FixEngine adapters
  ├── Validator adapters
  └── audit event writer
        ↓
Ephemeral Artifacts + Durable Production Metadata
```

The API never performs heavy PDF work inline. A worker never trusts a browser-provided measurement or PASS/FAIL result.

## 3. Domain Contracts

### 3.1 PrintPreset

A Print Preset is immutable and versioned. At minimum it contains:

- `presetId`, `version`, `status`, `productType`.
- target effective image PPI and bleed per edge.
- target PDF/X state.
- color policy and, for production presets, ICC identity/hash.
- later: black strategy, total ink coverage, spot/overprint policy and geometry.

POC presets are explicitly marked `poc-only`; they are not print-provider recommendations. Runtime threshold overrides receive a distinct development-only identity and must not masquerade as the original preset version.

### 3.2 Analysis / UDF

Parser output contains observations and source evidence only. It never embeds a production verdict. Source paths are worker-local and must be removed from persisted/report projections.

### 3.2.1 Target Geometry

PDF MediaBox/TrimBox dimensions are observations, not sufficient evidence of design intent. Every new Web job carries a user-confirmed immutable Target Geometry containing a standard/custom size ID, finished width and height in millimetres, source and contract version.

- Product/Print Preset controls PPI, bleed, color and PDF/X policy.
- Target Geometry independently controls finished Trim Size and the physical scale used for placed-image PPI.
- If PDF and target aspect ratios differ by no more than 2%, the service may offer confirmed whole-page proportional normalization.
- If the ratio exceeds that tolerance, geometry and bleed repair are `manual`; the engine never applies non-proportional stretching.
- Parser UDF remains unchanged. Rule policy records the target plus per-page observed size, scale and compatibility so production intent never contaminates parser observations.

### 3.3 RuleSet and RuleExecution

Every run emits:

```json
{
  "ruleSet": {"ruleSetId": "core-preflight", "version": "0.2.0-alpha"},
  "policy": {"printPreset": {}},
  "ruleExecutions": [
    {
      "ruleId": "IMAGE.LOW_EFFECTIVE_DPI",
      "ruleVersion": "1.1.0",
      "outcome": "FAIL",
      "issueCount": 1
    }
  ]
}
```

An issue adds localized presentation-independent evidence, severity, confidence and fix safety. Safety is constrained to `auto`, `confirm` or `manual`.

### 3.4 FixPlan

A Fix Plan is an immutable decision snapshot:

- source artifact hash;
- analysis ID, preset and rule-set versions;
- selected fix actions and user decisions;
- target engine/adapter and configuration;
- expected validation gates.

Changing a selection creates a new plan version. Workers do not infer new high-risk actions after approval.

### 3.5 Artifact and Validation

Artifacts are immutable references with content hash, MIME, byte size, lifecycle class and expiry. Validation records distinguish:

- `internal_preflight`;
- `syntax`;
- `render_regression`;
- `pdfx_external`;
- `printer_outcome`.

The system never derives an external or printer result from an internal result.

## 4. Job State Machine

```text
created
  → uploading
  → queued
  → analyzing
  → awaiting_decision
  → fixing
  → validating
  → ready | partial | failed
  → expired | deleted
```

Transitions use optimistic concurrency or an equivalent compare-and-set guard. Replayed queue messages are idempotent by `jobId + stage + inputHash + planVersion`.

`ready` means required internal checks completed. It does not imply independent PDF/X validation unless that result is separately `passed`.

## 5. API Surface (planned)

```text
POST   /v1/uploads                 create short-lived upload authorization
POST   /v1/jobs                    bind uploaded artifact and Print Preset
GET    /v1/jobs/{jobId}            state and safe progress projection
GET    /v1/jobs/{jobId}/report     analysis/issues/validation projection
POST   /v1/jobs/{jobId}/decisions  create immutable Fix Plan
POST   /v1/jobs/{jobId}/execute    enqueue approved plan
POST   /v1/jobs/{jobId}/download   create short-lived download URL
DELETE /v1/jobs/{jobId}/artifacts  request immediate content deletion
POST   /v1/jobs/{jobId}/feedback   rule/fix/production outcome feedback
```

Uploads and downloads use object storage directly. API responses never return internal bucket keys or durable public URLs.

## 6. Storage and Retention

Two data classes are intentionally separate:

### Ephemeral content

- source PDF: 1–6 hours;
- extracted images and intermediates: 1 hour;
- generated candidate: up to 24 hours;
- preview: only when required, with a short TTL.

Objects have provider lifecycle rules plus a reconciliation cleanup worker. Immediate delete removes all content objects and invalidates download authorization.

### Durable production intelligence

Allowed: hashes, counts, dimensions, issue/rule/fix versions, timings, errors, decisions and outcomes.

Disallowed by default: PDF bytes, artwork text, image content, brand/customer identity, thumbnails and complete object coordinates capable of reconstructing a design.

## 7. Worker Isolation

- One untrusted document per resource-limited process or container.
- Hard limits for input bytes, page count, decompressed bytes, rendered pixels, CPU, memory and wall time.
- No shared PyMuPDF Document across threads.
- Read-only source mount; separate write-only attempt directory.
- Network disabled unless a stage explicitly needs an approved external service.
- Tool stdout/stderr is sanitized before durable logging.

## 8. Adapter Boundaries

Domain services depend on interfaces, not vendor types:

```python
class ParserAdapter:
    def analyze(self, source: ArtifactRef) -> Analysis: ...

class FixAdapter:
    def execute(self, source: ArtifactRef, plan: FixPlan) -> FixResult: ...

class ValidatorAdapter:
    def validate(self, artifact: ArtifactRef, target: ValidationTarget) -> ValidationResult: ...
```

Current PyMuPDF/Ghostscript code remains a POC adapter. Closed-source deployment requires the license decision in ADR-005 or a replacement adapter.

## 9. Failure Policy

Errors use stable categories: `user_file`, `unsupported`, `resource_limit`, `timeout`, `engine`, `third_party`, `validation_failure`, `system`.

- A failed attempt never overwrites or relabels the source.
- Retry only deterministic/transient stages and preserve attempt identity.
- Validation failure publishes `partial` only when the artifact remains safe to inspect and risks are explicit; otherwise it publishes `failed`.
- Cleanup failure is security-relevant and alerts independently from processing success.

## 10. Implementation Sequence

1. Versioned Print Preset and Rule Set — implemented in the current increment.
2. Stable domain schemas and serialization tests.
3. Adapter protocols around current parser/fixer/validator functions.
4. Local in-process Job service for contract tests.
5. Production API with direct-upload authorization.
6. Queue and isolated worker runtime.
7. Artifact TTL and deletion reconciliation.
8. Designer diagnosis and approval UI.
9. External PDF/X validator and real Print Presets.

Each step must remain runnable without an LLM and include deterministic fixtures.

## 11. Verification Strategy

- Unit: presets, schema validation, rule boundaries and safety enums.
- Contract: identical UDF + preset + rule set yields identical result.
- Integration: controlled PDFs through analyze → rules → fix → analyze → validate.
- Regression: real authorized PDFs classified by expected evidence and human adjudication.
- Security: malformed PDFs, decompression/resource attacks, cross-tenant access and TTL failure.
- Production: external PDF/X comparison and printer acceptance feedback.
