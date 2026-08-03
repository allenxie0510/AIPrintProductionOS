# AI Print Production OS — Project Memory

- Version: 1.1.0-alpha
- Status: Local Web MVP complete; production hardening active
- Strategy: PDF first
- Last updated: 2026-08-03

## Mission

把现代设计工具导出的 PDF 转化为可解释、可修复、可复检的印刷就绪候选文件，让设计师在交付印厂前看见并控制生产风险。

产品不是在线设计编辑器或云盘。产品是任务型 PDF 印前诊断与优化工具，以及逐步演进的 Print Production OS。

## Current Product Contract

```text
PDF
  → Evidence-bearing Analysis
  → Versioned Rules + Print Preset
  → Risk-tiered Fix Plan
  → Immutable Derivative
  → Re-analysis + Validation
  → Candidate PDF + Audit Report
  → File Expiry / Deletion
```

### Alpha promise

检查并修复常见 PDF 印前问题，生成经过自动化复检的印刷就绪候选文件。

### The product never claims

- 修改 metadata 就能恢复真实图片细节。
- 相似字体可以静默替代原字体。
- PDF/X 标签等于独立合规验证。
- 一个通用 CMYK Profile 适合所有印刷条件。
- AI 可以无确认地改变原始设计区域。

## Source of Truth

优先级从高到低：

1. [Project Constitution](docs/00-project/constitution.md)
2. Accepted ADR
3. [Alpha PRD](docs/01-product/alpha-prd.md)
4. Architecture and engine specifications
5. Sprint and test specifications
6. Source code

历史聊天、旧 bootstrap prompt 和已标记 Superseded 的文档不是规范。

## Architecture Invariants

- Parser 只观察；Rule Engine 判定；Fix Engine 修改派生文件；Validator 复检。
- LLM 只解释、建议和编排人工决策，不直接修改 PDF。
- 原 PDF 不覆盖；源文件和派生文件分别记录哈希与 provenance。
- 每次诊断绑定不可变的 Print Preset、Rule Set 和规则版本。
- 修复安全等级仅为 `auto`、`confirm`、`manual`。
- 不可信 PDF 在资源受限的独立进程或容器中处理。
- 上传和输出文件默认临时保存，结构化生产数据按隐私策略保留。
- PDF/X 只能在独立验证器通过后标记为 `validated`。

## Current Status

Completed:

- PDF Preflight POC and controlled fixture.
- UDF 0.1 parser and six core issue categories.
- Effective PPI verification at 84.67 PPI.
- Safe solid-color bleed, crop marks and PDF/X-4 candidate path.
- qpdf/Poppler verification and automated tests.
- Alpha PRD.

In progress:

- Durable queue and object-storage adapters.
- PDF engine license decision and worker-container isolation.
- Independent PDF/X validation and print-provider presets.

MVP delivered:

- Responsive designer Web workflow.
- Ephemeral PDF jobs with token-scoped access, SQLite metadata and TTL cleanup.
- Upload → analyze → review → controlled fix → re-analyze → validate → download → delete.
- Feedback capture and privacy-safe metadata retention after artifact deletion.

Release gates:

- Artifex commercial license, compliant open-source model, or approved replacement stack.
- Independent PDF/X validator.
- Two print-provider-reviewed Alpha Print Presets and ICC profiles.
- Production isolation, temporary storage and deletion audit.
- Real-world regression corpus and printer acceptance testing.

## Current Development Policy

Alpha development is authorized when a change:

- is traceable to the accepted PRD or an accepted ADR;
- preserves architecture invariants;
- includes proportional automated validation;
- does not bypass licensing, privacy or external validation release gates.

Architecture boundary changes require an ADR. A new input format or changed product promise requires an RFC and PRD update before implementation.

## Key Links

- [Specification index](docs/README.md)
- [Alpha PRD](docs/01-product/alpha-prd.md)
- [System architecture](docs/02-architecture/system-architecture.md)
- [Technical feasibility report](docs/05-testing/technical-feasibility-report.md)
- [Architecture decisions](docs/decisions/README.md)
- [Current POC validation](docs/05-testing/poc-validation.md)
