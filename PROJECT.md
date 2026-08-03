# Project Memory

## Product

AI Print Production OS 是一个 PDF-first 的印前分析、规则决策、受控修复与审计平台。

## Mission

让非印前专家也能知道文件为什么不能安全生产、哪些问题能自动修复、哪些必须人工确认，并为每次转换保留可追溯证据。

## Product Boundary

- 当前输入：PDF。
- 当前核心：Preflight Parser + Rule Engine + Fix Planner + Fix Engines + Validation。
- AI 职责：解释、建议、问答和 QA 编排。
- AI 不直接修改 PDF，不绕过规则或人工审批。
- Figma/Canva/HTML 语义重建不属于当前 MVP。

## Architecture

```text
Web/API -> Upload -> Queue -> Isolated PDF Worker
                           -> Parser -> UDF
                           -> Rule Engine -> Issues
                           -> Fix Planner -> Fix Engines
                           -> Re-parse + Validate + Render Diff
                           -> PDF + Audit Report

AI Decision Layer reads UDF/issues and explains decisions.
```

详见 [`docs/02-architecture/system-architecture.md`](docs/02-architecture/system-architecture.md)。

## Current Status

- PDF Preflight POC：完成。
- 统一 JSON/UDF 0.1：完成 POC 版。
- 规则引擎：完成 6 类核心规则验证。
- 修复：完成纯色出血、裁切标记、CMYK、字体嵌入和 PDF/X-4 候选。
- 独立 PDF/X 合规验证：未完成，是 Alpha 门槛。
- Artifex AGPL/商业许可决策：未完成，是 Alpha 门槛。

## Current Sprint

[`docs/06-sprints/sprint-0.md`](docs/06-sprints/sprint-0.md) - 仓库规范化、POC 固化和 Alpha 进入条件。

## Coding Rules

- 原始 PDF 永不覆盖；所有修改生成带哈希和 provenance 的派生版本。
- 业务判断写入版本化规则，不散落在 UI、Prompt 或 Worker 中。
- 每个 issue 必须有 code、severity、evidence、confidence 和 fix safety。
- 高风险修复必须预览并确认。
- 修改架构边界前提交 RFC/ADR。
- 修复后必须重跑解析、规则、结构检查和视觉回归。

## Key Links

- [Specification index](docs/README.md)
- [Feasibility report](docs/05-testing/technical-feasibility-report.md)
- [Architecture decisions](docs/decisions/README.md)
- [Knowledge graph](docs/knowledge/issue-rule-fix-validation.md)
- [POC verification evidence](output/poc/verification.json)
