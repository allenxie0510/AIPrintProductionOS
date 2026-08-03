# 在线 PDF 印前诊断与优化工具 — Alpha PRD

- 产品：AI Print Production OS
- 文档版本：0.2.1
- 状态：Accepted for Alpha development
- 日期：2026-08-03
- 目标周期：6–8 周
- 适用范围：设计师专属 Web App，PDF-first

## 1. 文档目的

本 PRD 将已完成的 PDF Preflight POC 收敛为可开发、可验证的 Alpha 产品。它定义产品承诺、用户流程、功能边界、验收标准、数据边界和发布门槛。

本文件不是对历史讨论的复制。若本文件与已接受的 Constitution 或 ADR 冲突，以后者为准。

## 2. 产品定义

### 2.1 一句话定位

一个不长期托管设计文件的任务型 AI 印前处理 Web App：设计师上传 PDF，系统完成可解释的诊断、受控修复和复检，用户下载印刷就绪候选文件后，生产文件按策略自动删除。

### 2.2 核心价值

设计师不需要掌握完整印前知识，也能回答：

1. 这个 PDF 为什么存在印刷风险？
2. 哪些问题可以安全自动修复？
3. 哪些问题需要本人、原设计文件或印厂介入？
4. 修复后哪些检查已经通过，哪些风险仍然存在？

### 2.3 Alpha 产品承诺

> 检查并修复常见 PDF 印前问题，生成经过自动化复检的印刷就绪候选文件。

Alpha 不承诺“一键生成认证合规 PDF/X”，也不保证印厂必然接受。只有通过独立合规验证时，界面才允许显示相应的“已验证”状态。

## 3. 产品原则

1. **PDF first**：Alpha 主文件输入仅支持 PDF。
2. **不伪造质量**：修改 DPI metadata 或进行普通重采样不能消除原始低有效 PPI 事实。
3. **原文件不可变**：所有修复生成新的派生文件，可撤销、可追踪。
4. **成品尺寸由设计师确认**：PDF 页面坐标不能替代生产意图；Trim Size 必须显式选择，自动识别只能作为建议。
5. **规则优先于 AI**：解析器提供证据，规则引擎判定，修复引擎修改，验证器复检；LLM 只解释和辅助决策。
6. **不静默替换字体**：缺少精确字体时不得自动使用相似字体。
7. **按风险分级自动化**：修复只允许 `auto`、`confirm`、`manual` 三种安全等级。
8. **修复后必须复检**：Analyze → Plan → Repair → Analyze Again → Validate → Export。
9. **临时处理**：默认不长期保存 PDF、提取图片或最终生产文件。
10. **目标印刷条件是配置**：CMYK、出血、目标 PPI 和 PDF/X 由版本化 Print Preset 决定。
11. **证据决定声明**：PDF/X 标识和 OutputIntent 只能产生候选状态，不能替代独立验证。

## 4. 目标用户与场景

### 4.1 核心用户

- 独立平面设计师：需要在交付印厂前自检文件。
- 市场与品牌设计师：主要使用 Canva、Figma、Adobe Express 等工具，缺少专业印前经验。
- 设计工作室与代理商：需要减少反复退稿并保留处理记录。

### 4.2 次级用户

- 印刷经纪和接单人员：需要快速判断客户文件风险。
- 印厂印前人员：需要标准化收件检查和确认依据。

### 4.3 关键 Job-to-be-Done

> 当我准备把设计稿发给印厂时，我希望在几分钟内知道文件能否安全生产，并在不破坏设计的前提下解决可自动处理的问题。

## 5. Alpha 目标与非目标

### 5.1 目标

- 建立从 PDF 上传到报告、修复、复检、下载和删除的任务闭环。
- 对页面框、颜色、图片有效 PPI、字体、PDF/X 和基础透明度风险提供可解释证据。
- 将确定性安全修复与需要确认、必须人工处理的修复清楚分开。
- 记录结构化生产数据，不默认保留用户设计内容。
- 用真实印厂反馈验证 Print-Ready Success Rate。

### 5.2 非目标

- 在线设计编辑器、素材库、文件夹或永久项目空间。
- Figma、Canva、PSD、AI、SVG、HTML 原文件重建。
- 任意字体自动转曲或相似字体自动替换。
- 任意场景的生成式出血。
- 把低分辨率图片描述为“恢复真实 300 DPI”。
- 完整专色、叠印、复杂透明度和 RIP 行为修复。
- 未经外部工具及印厂验证的“100% 可印”保证。

## 6. 输入、输出与限制

### 6.1 主文件输入

Alpha 仅接受 PDF。默认限制：

- Free：最大 100 MB、最多 5 页。
- Alpha 测试账户：最大 300 MB、最多 20 页。
- 加密 PDF：提示用户输入合法密码或上传未加密版本；不得绕过权限。
- 畸形、恶意或资源异常文件：隔离处理并按明确错误码终止。

限制必须可通过部署配置调整，不写死在 UI。

### 6.2 替换图片输入

低分辨率图片修复流程可以接受 JPG、PNG、TIFF、WebP 作为替换素材。它们不能作为完整印刷版式主输入。

### 6.3 输出

- 结构化诊断报告。
- 可下载的人类可读报告。
- 修复计划及用户决策记录。
- 修复后的 PDF/X 候选文件。
- 独立验证结果（接入验证器后）。
- 文件与修复 provenance：源/输出哈希、规则版本、引擎版本、Print Preset 和 ICC 标识。

## 7. 用户主流程

```text
选择 PDF
  → 本地基础检查
  → 直传临时对象存储
  → 选择产品/印刷预设并确认成品裁切尺寸
  → 在线诊断
  → 查看问题、证据和风险
  → 选择或确认修复
  → 生成派生文件
  → 自动重新解析与验证
  → 前后对比
  → 下载候选文件和报告
  → 立即删除或到期自动删除
```

### 7.1 任务状态

`created → uploading → queued → analyzing → awaiting_decision → fixing → validating → ready | partial | failed → expired | deleted`

- `ready`：所有必需内部检查通过，但不等于 PDF/X 外部合规。
- `partial`：生成了可下载派生文件，但仍有 FAIL、需人工修复或外部验证未通过。
- `failed`：未生成可安全发布的派生文件。
- `expired/deleted`：文件不可再下载，结构化记录按策略保留。

## 8. 信息架构与页面

### 8.1 上传页

- 拖拽或选择 PDF。
- 显示文件名、大小、页数和加密状态。
- 选择产品类型：名片/宣传单、画册、海报、大幅喷绘、自定义。
- 选择 Print Preset；普通模式展示业务名称，专业模式展示 ICC、PDF/X、出血和 PPI。
- 必须选择目标成品尺寸（Trim Size）：A3/A4/A5、B5 ISO、B5 JIS、名片或自定义毫米尺寸，并明确横竖方向。
- 页面尺寸自动识别只显示为 PDF 观察值，不得静默替代用户确认。Figma/Canva 的像素画布尤其需要用户确认实际印刷尺寸。
- 明确提示文件保留时间及“上传不是永久保存”。

### 8.2 处理页

- 展示上传、排队、解析、规则、修复、验证各阶段状态。
- 显示预计时间和已用时间，不展示虚假精度。
- 允许安全取消任务；取消后触发文件清理。

### 8.3 诊断页

- 展示 Overall Readiness Score，但任何 FAIL 不得被高分隐藏。
- 按 Resolution、Color、Bleed、Font、Geometry、Transparency、PDF Compliance 分组。
- 每个 issue 展示：问题、影响、证据、规则版本、建议、修复安全级别、置信度和剩余风险。
- 支持定位到页面和对象；图片问题展示有效 PPI 与实际放置尺寸。

### 8.4 修复确认页

- `auto` 修复默认勾选但可取消。
- `confirm` 修复必须显示预览、影响和用户确认。
- `manual` 修复不提供虚假按钮，给出返回设计软件或联系印厂的步骤。
- 用户选择形成不可变 Fix Plan 快照。

### 8.5 结果页

- 展示修复前后分数、问题变化、验证状态和失败项。
- 支持页面级前后对比和放大查看。
- PDF/X 分为 `not_requested`、`candidate`、`validated`、`validation_failed`。
- 支持下载 PDF 和报告，以及“下载后立即删除所有文件”。

## 9. 功能需求与验收标准

### FR-001 PDF 接收与基础校验（P0）

系统必须检查 MIME、文件签名、大小、页数、加密状态和解析资源限制。

验收：

- 非 PDF、超限和需要密码的文件返回不同错误码及可操作说明。
- 应用服务器不代理大文件正文；生产方案使用短时 signed URL 直传。
- 上传对象使用随机 key，任务之间不可互相访问。

### FR-002 统一解析（P0）

系统必须解析源文件哈希、页数、页面框、图片及其每次放置、字体、颜色空间、OutputIntent、PDF/X 声明和基础风险信号。

验收：

- 图片报告像素尺寸、页面放置尺寸和 Effective PPI，而非只读取 metadata DPI。
- 当用户确认 Target Geometry 且页面比例兼容时，图片放置毫米尺寸和 Effective PPI 必须按目标成品尺寸计算，而不是按 Figma 导出的 PDF point/px 映射计算。
- 显式页面框与 PDF 阅读器默认框分开记录。
- 观察数据与规则结论分离，解析器不输出生产 PASS/FAIL。

### FR-003 Print Preset（P0）

每次诊断必须绑定不可变的 Print Preset 版本和用户确认的 Target Geometry。Print Preset 至少包含产品类型、目标 PPI、出血、PDF/X 目标和颜色策略；Target Geometry 至少包含标准尺寸 ID/自定义、宽高毫米、来源和版本。

验收：

- 相同 UDF 与相同 Print Preset/Rule Set 得到确定性相同结果。
- 结果报告包含 `presetId` 和 `presetVersion`。
- 结果报告包含目标成品宽高、PDF 当前页面宽高、比例差异和计算 PPI 使用的尺寸依据。
- 目标尺寸与 PDF 尺寸不同但比例在 2% 容差内时，可由用户确认后等比规范化；比例超出容差时必须返回 `manual`，不得非等比拉伸。
- 不允许把通用 CMYK Profile 宣称为所有印刷条件的正确默认值。

### FR-004 版本化规则引擎（P0）

规则必须使用稳定 ID 和版本，输出证据、严重级别、置信度及修复安全级别。

验收：

- 每个 issue 可追踪到唯一 `ruleId` 与 `ruleVersion`。
- 安全级别只能是 `auto`、`confirm` 或 `manual`。
- 每条新增规则同时提供正例、负例和边界测试。

### FR-005 页面与出血诊断（P0）

系统同时检查 MediaBox、CropBox、TrimBox、BleedBox、所需出血和页面边缘内容。

验收：

- 没有 BleedBox 但内容已超出 TrimBox 时，不得直接判定必须扩图。
- TrimBox 来源不明确时，只能进入 `confirm` 或 `manual`。
- PDF 页面尺寸与用户确认的成品尺寸不同但比例兼容时，必须先显示差异并由用户确认等比规范化；比例不兼容时不得自动缩放或补出血。
- 输出显示四边实际出血数值。

### FR-006 图片分辨率（P0）

系统按内容放置计算 Effective PPI，并按 Print Preset 阈值判断。

验收：

- POC 样本的 600×400 px 图片以 180×120 mm 放置时结果约为 84.67 PPI。
- 仅修改 metadata 后重新分析，问题仍然存在。
- 位图文字、线稿、二维码与照片可以使用不同策略；未知类型默认需要确认。

### FR-007 颜色诊断与转换（P0/P1）

系统识别 RGB、CMYK、Gray、Lab、Separation/Spot 和 DeviceN 基础证据。转换由目标 ICC 和 Print Preset 驱动。

验收：

- RGB 图片、矢量和文本分别记录证据。
- 小字号黑色文字、细线、二维码和条码不得无控制地转成四色黑。
- 已有 CMYK 与专色默认保留或按明确策略处理。
- 转换后重新解析颜色空间并保留 ICC 哈希。

### FR-008 字体安全（P0）

系统检查字体嵌入、类型和可恢复性。

验收：

- 精确字体匹配必须验证 PostScript Name、字形/字宽信息、许可和视觉回归。
- 只有相似字体时不得自动替换。
- 字符映射不可恢复时返回 `manual`，不得承诺自动转曲。
- 静默字体替换次数必须为 0。

### FR-009 安全修复（P0）

Alpha 支持已确认 TrimBox/BleedBox、裁切标记、均匀纯色背景延展、Print Preset 驱动的颜色规范化和 PDF/X 候选输出。

验收：

- 所有修改写入新派生文件，不覆盖源文件。
- 纯色出血仅在边缘分类满足自动阈值时执行。
- 裁切标记必须是位于最终内容流最上层的矢量路径，放置在 BleedBox 外侧，并使用 Registration `/All` 分色；其替代色为 C/M/Y/K 各 100%，不得使用普通单黑或位图标记。
- 后续 CMYK/PDF/X 候选转换必须保留 Registration `/All` 分色与裁切标记的可见性。
- 所有修复记录输入/输出哈希、规则、引擎和配置。

### FR-010 低分辨率图片处理（P1）

处理顺序为：上传高质量替换图 → 传统高质量缩放 → 保真 AI 超分 → 用户明确同意后的生成式增强。

验收：

- Logo、二维码、条码、位图文字、工程图禁止默认生成式增强。
- 超分后根据新增真实像素和原放置尺寸重新计算 Effective PPI。
- 报告同时保留原始 PPI、处理方式、模型版本和“推测细节”警告。
- 用户可预览并撤销。

### FR-011 分级出血修复（P1）

按以下顺序尝试：仅修正框定义 → 对象级扩展 → 边缘像素/纹理延展 → 局部内容感知 → AI 仅生成 bleed mask 区域。

验收：

- 原 Trim Area 像素/对象保持锁定，AI 不得重绘原设计。
- 每次修复展示方法、置信度和 Safe/Review/Manual 结果。
- 人脸、文字、Logo、建筑轮廓等贴边时不得默认镜像扩展。

### FR-012 修复后验证（P0）

每个派生文件必须重新解析、重跑规则、执行语法检查和渲染差异检查。

验收：

- 未完成复检的文件不可进入 `ready`。
- 内部验证、外部 PDF/X 验证和印厂接受是三个独立结果。
- 新增 PDF/X 声明或 OutputIntent 只能产生 `candidate`。

### FR-013 报告与可解释性（P0）

报告必须同时服务非印前设计师和专业用户。

验收：

- 每个问题回答“是什么、为什么、怎么处理、还剩什么风险”。
- 技术证据可展开，普通说明默认可读。
- 评分展示修复前后维度分，不声称 100 分等于必然可印。

### FR-014 临时文件生命周期（P0）

默认策略：源 PDF 1–6 小时；中间文件与提取图片 1 小时；最终 PDF 24 小时；结构化诊断与审计 30–90 天。

验收：

- 每类对象设置服务端 TTL，并有兜底清理任务。
- 用户可触发立即删除；删除状态可审计但不保留内容。
- 下载 URL 短时有效，不可枚举，不写入持久日志。

### FR-015 Production Intelligence（P0）

系统长期保留必要的结构化生产数据，不默认保留设计内容。

验收：

- 保存 Job、FileMetadata、Analysis、Issue、RuleExecution、FixAction、OutputConfig、Validation、Feedback、ProductionOutcome 和 ErrorLog。
- 规则、引擎、模型、Print Preset 和 ICC 全部版本化。
- 不保留正文、品牌名称、图片、缩略图或可重建设计的完整坐标集，除非获得单独授权。
- 模型训练数据必须单独 opt-in，不能由产品改进授权替代。

### FR-016 用户反馈与生产结果（P1）

反馈与具体规则和修复绑定，并允许记录印厂是否接受。

验收：

- 支持 `accepted`、`partially_correct`、`incorrect`、`undone`。
- 支持 `printer_accepted`、`printer_rejected`、`printed_successfully`、`printed_with_issues`、`unknown`。
- 印厂退回原因使用结构化枚举并允许备注。

## 10. 修复安全矩阵

| 能力 | Alpha 等级 | 关键前提 |
|---|---|---|
| 已确认 TrimBox 后添加裁切标记 | auto | 页面几何已确认 |
| 纯色背景扩展 3 mm | auto | 高置信均匀边缘 |
| 只补充正确的 BleedBox 定义 | auto/confirm | 内容已实际延伸 |
| RGB → 目标 CMYK | confirm | Print Preset、ICC、预览 |
| 精确字体嵌入 | confirm | 身份和许可匹配 |
| 相似字体替换 | manual/confirm | 禁止静默执行 |
| 传统图片缩放 | confirm | 不宣称恢复细节 |
| 保真 AI 超分 | confirm | 类型白名单和预览 |
| 生成式图片增强 | confirm/manual | 明确接受推测细节 |
| AI 出血扩图 | confirm/manual | 仅修改 bleed mask |
| PDF/X 候选导出 | confirm | 独立验证前仅 candidate |

## 11. 数据模型概要

```text
Job
├── FileMetadata (anonymous technical features)
├── Analysis
│   └── Issue[]
├── RuleExecution[]
├── FixPlan
│   └── FixAction[]
├── OutputConfig / PrintPreset snapshot
├── Artifact[] (ephemeral object references)
├── Validation[]
├── Feedback[]
├── ProductionOutcome
└── ErrorLog[]
```

### 11.1 必需追踪字段

- `jobId`, `tenantId`, `sourceSha256`, `createdAt`。
- `presetId`, `presetVersion`, `ruleSetId`, `ruleSetVersion`。
- `ruleId`, `ruleVersion`, `engineName`, `engineVersion`, `modelVersion`。
- `stageDurationMs`, `estimatedCost`, `actualCost`。
- `beforeValue`, `afterValue`, `confidence`, `userDecision`。
- `internalValidation`, `externalValidation`, `printerOutcome`。

## 12. 事件体系

### 12.1 业务事件

`job_created`, `file_uploaded`, `analysis_completed`, `fix_selected`, `fix_applied`, `fix_undone`, `preview_opened`, `file_downloaded`, `files_deleted`, `feedback_submitted`。

### 12.2 生产事件

`issue_detected`, `rule_evaluated`, `engine_started`, `engine_completed`, `validation_failed`, `export_completed`, `cleanup_completed`。

### 12.3 质量结果

`internal_preflight_passed`, `user_accepted`, `printer_accepted`, `printer_rejected`, `printed_successfully`, `printed_with_issues`。

事件不得包含设计正文、图片内容、客户名称或原始 signed URL。

## 13. 非功能需求

### 13.1 安全与隔离

- 不可信 PDF 在独立、资源受限的进程或容器中处理。
- 设置 CPU、内存、文件解压大小、像素数、页数和执行超时上限。
- PyMuPDF 不跨线程共享 Document。
- 文件传输和对象存储加密；最小权限访问；租户隔离。
- 日志默认不记录文件名、正文、原始命令中的敏感 URL。

### 13.2 性能目标

- Time to First Diagnosis：P50 ≤ 30 秒，P95 ≤ 120 秒（≤100 MB、≤5 页，排除 AI）。
- 普通确定性修复：P50 ≤ 60 秒。
- 处理阶段必须分段计时，AI 等待与队列等待单独报告。
- 失败必须可恢复或提供明确错误，不允许无限排队。

### 13.3 可用性与可观测性

- 所有任务具有幂等键；重复回调不能产生重复修复。
- Worker 失败不改变源文件，可从阶段边界重试。
- 记录错误分类：system、unsupported、user_file、third_party、timeout、resource_limit、validation_failure。

### 13.4 兼容性

- Alpha 浏览器：当前及前一主版本 Chrome、Edge、Safari、Firefox。
- PDF 输入以真实回归集定义支持范围，不按“PDF 1.x”标签笼统保证。

## 14. 技术架构约束

```text
Browser / Web UI
  → Signed Upload API
  → Temporary Object Storage
  → Job API + Queue
  → Isolated Python Worker
       → Parser Adapter
       → UDF
       → Versioned Rule Engine
       → Fix Planner
       → PDF / Color / Font / Image Adapters
       → Internal + External Validators
  → Report API + Short-lived Download URL
```

- 浏览器负责交互、预览和轻量检查；服务器负责 ICC、字体、复杂 PDF 重写、AI 和最终导出。
- API/UI 不在线执行 CPU 重处理。
- 具体 PDF SDK 位于 Adapter 后，避免领域层与 PyMuPDF/Ghostscript 强耦合。
- Ghostscript/PyMuPDF 仅作为当前 POC 技术，不代表闭源生产许可已经解决。

## 15. 核心指标

### 15.1 北极星指标

**Print-Ready Success Rate**：成功下载、内部复检通过且关键修复未被撤销的任务比例。Beta 后以 Printer Acceptance Rate 作为更强结果指标。

### 15.2 质量指标

- 核心诊断准确率 ≥ 95%。
- 严重问题漏报率 < 2%。
- Safe Fix 自动化测试通过率 ≥ 98%。
- 修复后 PDF 语法通过率 ≥ 99%。
- 静默字体替换 = 0。
- Safe Fix 撤销率 < 5%。

### 15.3 漏斗与效率

- 诊断完成率 ≥ 85%。
- 修复启动率 ≥ 50%。
- 修复后下载率 ≥ 70%。
- Time to First Diagnosis、Time to Print-ready、Queue Wait、各引擎耗时。
- Cost per Job、AI Cost per Job、不可恢复失败率。

## 16. Alpha Go/No-Go

进入外部 Alpha 前必须同时满足：

1. 完成 Artifex 商业许可、合规开源方案或替代引擎决策。
2. 选定独立 PDF/X 验证器；不能用 qpdf 或 veraPDF 代替 PDF/X 合规验证。
3. 与至少两种真实产品/印厂要求建立版本化 Print Preset。
4. 建立至少 200 份匿名化或获授权真实 PDF 回归集。
5. 核心规则具备正例、负例、边界例和人工裁决标准。
6. 文件 TTL、立即删除、租户隔离和清理审计通过测试。
7. P0 验收标准全部通过，未解决项在界面清楚标识。

## 17. 6–8 周交付路线

### Sprint 0：治理、许可与验证方案

- 完成架构/许可决策和两套 Print Preset。
- 确定外部 PDF/X 验证方案。
- 固化免责声明和数据授权边界。

### Week 1：POC 产品化基础

- 版本化 Print Preset、Rule Set、Issue、Rule Execution。
- 建立 Adapter 接口和确定性回归测试。

### Week 2：Web 任务闭环

- 上传、对象存储、Job API、队列、诊断页和 TTL 清理。

### Week 3：安全修复与复检

- 页面框、裁切标记、颜色和 PDF/X 候选；修复后重跑规则。

### Week 4：图片对象与 Effective PPI

- 原位替换、传统缩放、重新计算 PPI 和版式回归。

### Week 5：保真超分与基础出血

- 内容分类、AI 安全门、预览撤销、对象/像素出血。

### Week 6：字体安全与外部验证

- 精确字体身份、上传字体、禁止静默替代、PDF/X 外部验证。

### Week 7–8：数据、稳定性与印厂私测

- Production Intelligence、错误和成本观测。
- 30–50 个首批真实私测文件，逐步扩大回归集。
- 记录印厂接受/退回和误报漏报。

## 18. 依赖与待决策项

| 决策 | 状态 | 发布影响 |
|---|---|---|
| PyMuPDF/Ghostscript 商业许可或替代栈 | 未决 | Alpha 部署 Gate |
| 独立 PDF/X 验证器 | 未决 | 只能显示 candidate |
| 两个 Alpha Print Preset 及 ICC | 未决 | 颜色输出不可产品化 |
| 对象存储/队列供应商 | 可延后 | 不影响领域模型 |
| AI 超分模型及模型许可 | 未决 | P1 功能 Gate |
| 用户内容用于模型训练授权 | 默认禁止 | 需独立 opt-in |

## 19. POC 追溯

已验证：PDF 统一解析、六类问题检测、84.67 Effective PPI、纯色出血、裁切标记、RGB→CMYK/Gray、OutputIntent、PDF/X-4 候选、qpdf 语法检查，以及按 PDF 图片对象原位替换高分辨率原图后重新计算 Effective PPI。

部分验证：原字体 TTF/OTF 上传、签名和内部名称匹配，以及任务级字体路径已实现；精确字体嵌入的许可、字形/字宽身份和视觉回归仍未完成发布验证。

尚未验证：AI 超分、复杂出血、独立 PDF/X 合规、真实印厂接受、生产级隔离与临时存储。

本 PRD 继承 POC 的关键负面结论：低 PPI 不能伪修复；Nimbus Sans 代替 Helvetica 不是安全字体修复；PDF/X 元数据不是合规认证。

## 20. Definition of Done

一个 Alpha 功能只有同时满足以下条件才算完成：

- 规格、验收条件和风险等级已定义。
- 实现及单元/集成/回归测试完成。
- 对源文件无覆盖，provenance 完整。
- 修复后重新分析并通过规定验证。
- 文档、规则库和变更日志已更新。
- 不扩大隐私收集范围，不使用未批准许可组件。
