# AI Print Production OS - PDF 印前引擎技术可行性报告

- 日期：2026-08-03
- 结论等级：**有条件可行（Go with constraints）**
- 建议产品定义：**AI Preflight Engine / AI Print Production OS 的 PDF 第一阶段**

## 1. 执行结论

以“PDF 输入 -> 结构化分析 -> 规则判断 -> 有条件自动修复 -> PDF/X 输出候选 -> 报告”为 MVP，技术路线可行；以“任意设计文件 -> 语义级重建 -> 全场景无损自动修复”为 MVP，不可行。

本次 POC 已实测跑通以下闭环：

- 解析页面尺寸、MediaBox/CropBox/TrimBox/BleedBox、图片像素与落版 DPI、字体及嵌入状态、已使用颜色空间、PDF/X 声明与 OutputIntent，并输出统一 JSON。
- 规则引擎准确识别受控样本中的 RGB、未嵌入字体、84.67 DPI 图片、缺失 TrimBox、缺失 3 mm 出血和缺失 PDF/X 声明。
- 对“页面边缘为均匀纯色”场景自动扩展 3 mm 出血、增加裁切标记并设置页面框。
- 使用 ICC 色彩管理将 RGB 内容转换为 CMYK/Gray，嵌入替代字体，生成带 OutputIntent 的 PDF/X-4 候选文件。
- 输出通过 qpdf 语法与流编码检查；Poppler `pdfinfo` 识别为 PDF 1.6、PDF/X-4；Ghostscript `inkcov` 返回 CMYK 墨量。
- 低分辨率图片仍保持为问题，没有通过修改 DPI metadata 冒充真实修复。

最终输出的规则评分从 0 提升到 82；唯一剩余 FAIL 是原始图片有效分辨率不足。该结果证明“规则驱动、风险分级、允许保留未解决项”的产品模型成立。

## 2. 验证范围与方法

### 2.1 受控输入

POC 自生成一页 A4 PDF，故意包含以下已知事实：

| 事实 | 预期 |
|---|---:|
| 页面 | A4，210 x 297 mm |
| 图片 | 600 x 400 px |
| 图片落版尺寸 | 180 x 120 mm |
| 有效分辨率 | 约 84.67 DPI |
| 颜色 | DeviceRGB |
| 字体 | Helvetica / Helvetica-Bold，Base-14 未嵌入 |
| TrimBox / BleedBox | 未显式定义 |
| PDF/X / OutputIntent | 无 |
| 页面边缘 | 均匀蓝色，可做纯色延展 |

这比只拿一个未知来源 PDF 做演示更能判断误报、漏报和修复是否符合预期。

### 2.2 实测工具链

| 组件 | 实测版本 | POC 职责 |
|---|---:|---|
| PyMuPDF | 1.26.3 | 页面、图片、字体、对象和渲染解析 |
| pypdf | 6.10.0 | 页面合成、页面框与裁切标记写入 |
| Ghostscript | 10.07.1 | ICC 转换、字体处理、PDF/X 输出候选 |
| qpdf | 12.3.2 | PDF 结构/语法检查与低层 JSON 能力 |
| LittleCMS | 2.19 | Ghostscript/Pillow 背后的 ICC 色彩转换能力 |
| Poppler | 26.05.0 | 独立渲染与 `pdfinfo` 交叉检查 |

PyMuPDF 的 `get_image_info()` 能返回实际显示图片的 bbox、像素、颜色空间、变换矩阵和 xref，页面 API 也暴露 TrimBox/BleedBox 等信息，适合做高层业务解析；qpdf JSON 则能提供完整的 PDF 对象级表示，适合作为疑难文件的低层证据通道。[PyMuPDF Page API](https://pymupdf.readthedocs.io/en/latest/page.html) [qpdf JSON](https://qpdf.readthedocs.io/en/stable/json.html)

## 3. 实测结果

### 3.1 解析与规则命中

| 检查项 | 输入结果 | 输出结果 | 判定 |
|---|---|---|---|
| RGB 内容 | DeviceRGB | DeviceCMYK + DeviceGray | 技术修复成功，仍需印刷配置 |
| 字体嵌入 | 2 个字体未嵌入 | 全部存在嵌入程序 | 技术修复成功，但发生替代 |
| 图片有效 DPI | 84.67 | 84.67 | 正确保留 FAIL |
| TrimBox | 缺失 | 显式存在 | 成功 |
| BleedBox | 缺失 | 四边 3.0 mm | 成功 |
| 裁切标记 | 无 | 已生成 | 成功 |
| PDF/X | 无 | 声明 PDF/X-4 | 候选成功，未完成独立认证 |
| OutputIntent | 无 | 存在 | 成功 |
| PDF 语法 | 可读 | qpdf 无语法/流编码错误 | 成功 |

输入的 6 类预期 issue code 全部命中，没有漏项。最终仅保留 `IMAGE.LOW_EFFECTIVE_DPI`。

### 3.2 视觉交叉验证

最终文件同时由 PyMuPDF 和 Poppler 渲染。人工检查确认：

- 页面内容未裁断、未旋转、未错位。
- 四角裁切标记完整，标记位于页面外侧。
- 蓝色背景延展到出血区域。
- 字体、图片和文本仍可见，没有整页栅格化。
- Trim 区域与原输入在 150 DPI 渲染下的平均通道绝对差为 4.845/255；差异主要来自 ICC 转换和字体替代。这不是色彩准确性证明，只是版式回归信号。

### 3.3 关键负面发现

字体“自动嵌入”不是无条件安全。本次 Ghostscript 将缺失的 Helvetica/Helvetica-Bold 替换为 NimbusSans，再将替代字体嵌入。技术检查会通过，但字宽、换行、品牌字体和许可都可能改变。因此产品必须区分：

1. 原字体程序已在 PDF 内：已安全嵌入，无需修复。
2. 精确字体文件可用且许可允许：可嵌入，但需版式回归。
3. 只有替代字体：不得静默一键修复，只能生成预览并要求确认。
4. 转曲：会损失文本可编辑性/可搜索性并可能放大文件，只适合作为受控降级策略。

Ghostscript 官方说明默认会嵌入替代字体，也明确说明 PDF 输入下的字体处理受 `EmbedSubstituteFonts` 等参数影响。[Ghostscript 字体参数](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html)

## 4. 三个核心问题的回答

### 4.1 PDF 能否稳定解析为统一 JSON？

**可以，但 UDF 应是“印前诊断模型”，不是“可逆设计文件模型”。**

当前 POC 的 `udfVersion: 0.1-poc` 已覆盖：

- 文件哈希、版本、加密状态、页数。
- 页面 Media/Crop/Trim/Bleed 框及 mm/pt 单位。
- 图片 xref、像素、颜色空间、alpha、bbox、变换矩阵、有效 DPI。
- 字体名称、类型、编码、xref、字体程序字节数、嵌入状态。
- 已使用颜色空间与低置信度结构 token。
- 边缘均匀度和建议的出血策略。
- PDF/X 声明、OutputIntent、限制与证据置信度。

不能承诺完整恢复：Figma 组件、Auto Layout、Canva 模板、图层命名、约束、设计 token、文本语义和原始资源关系。这些信息通常已在 PDF 导出时丢失。

生产版 UDF 应增加：`parserVersion`、`ruleSetVersion`、`toolchain`、`sourceObjectRef`、`evidence`、`confidence`、`printPresetId`、`targetIccSha256`、`fixProvenance` 和每次派生文件哈希。不要把 qpdf 的完整对象 JSON直接暴露给业务层；它更适合审计和疑难诊断。[qpdf JSON 完整表示说明](https://qpdf.readthedocs.io/en/stable/json.html)

### 4.2 哪些修复可以“一键自动”？

| 能力 | 产品级自动化等级 | 前提/边界 |
|---|---|---|
| 设置 TrimBox/BleedBox | 条件自动 | 必须先确定成品尺寸，不能靠猜 |
| 裁切标记 | 自动 | 已确认 TrimBox、标记长度和 slug 规则 |
| 均匀纯色背景出血 | 自动 | 边缘分类高置信度；POC 已验证 |
| RGB -> CMYK | 条件自动 | 必须选择印厂/纸张/油墨 ICC、rendering intent、黑版策略并软打样 |
| 字体嵌入 | 条件自动 | 必须有精确字体及嵌入许可；替代字体需确认 |
| PDF/X 输出 | 条件自动 | 指定标准、OutputIntent，独立 validator 通过 |
| 图片超分 | 建议+确认 | 能改善感知质量，不能恢复不存在的真实细节 |
| 满版照片智能出血 | 建议+确认 | 需要镜像/生成式延展、主体保护和预览 |
| Logo/文字贴边页面 | 人工处理 | 自动延展不能解决安全边距和构图问题 |
| 复杂透明/专色/DeviceN | 专业预检 | 需要目标 RIP/标准验证与打样 |

Ghostscript 的 pdfwrite 使用 LCMS2 进行颜色转换，并支持 CMYK、Separation 和 DeviceN 的相关处理，但同一套转换策略会作用于不同对象，透明混合空间也会影响结果，因此不能把“转换完成”当作“颜色正确”。[Ghostscript 色彩管理](https://ghostscript.readthedocs.io/en/latest/VectorDevices.html) LittleCMS 本身是完整的 ICC 色彩管理引擎，采用 MIT 许可，适合做底层 CMM。[LittleCMS Color Engine](https://littlecms.com/color-engine/)

Real-ESRGAN 支持通用/动漫模型、tile、alpha、16-bit 和不同倍率，但其项目也提醒分块可能造成不一致；模型选择和人工 QA 必须进入规则与审阅流程。[Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN)

### 4.3 是否应以成熟开源组件为主？

**是，但不能只看“开源”，必须把许可、标准验证和进程隔离作为架构条件。**

最大的商业风险是 PyMuPDF/MuPDF 和 Ghostscript 都由 Artifex 以 AGPL 或商业许可双重授权。Artifex 明确表示闭源产品或 SaaS 使用 Ghostscript需要商业许可；PyMuPDF 官方也要求商业数据管线评估 AGPL义务或购买商业授权。[Ghostscript FAQ](https://ghostscript.com/faq/index.html) [PyMuPDF licensing FAQ](https://pymupdf.readthedocs.io/en/latest/faq/index.html)

因此有三条可选路线：

1. 购买 Artifex 商业许可，保留当前最高效率组合。
2. 解析层改为 qpdf/pikepdf + PDFium/Poppler 等组合，颜色/标准输出采购独立商业 SDK；qpdf 为 Apache-2.0。[qpdf License](https://qpdf.readthedocs.io/en/12.0/license.html)
3. 整个服务满足 AGPL 开源要求。是否足够必须由律师评估，不能由工程判断代替。

OpenCV 当前为 Apache-2.0，Real-ESRGAN 为 BSD-3-Clause，许可相对友好，但仍需核查模型权重、下游库和部署包中的第三方许可。[OpenCV](https://github.com/opencv/opencv) [Real-ESRGAN License](https://github.com/xinntao/Real-ESRGAN/blob/master/LICENSE)

## 5. 推荐生产架构

```text
Web / API
  -> Upload + malware/quota guard
  -> immutable object storage
  -> job queue
  -> isolated PDF worker process/container
       -> parser adapters
       -> UDF + evidence
       -> versioned rule engine
       -> fix planner (auto / confirm / manual)
       -> fix engines (box / color / font / image)
       -> independent validation + render diff
  -> output PDF + audit report
  -> AI explanation/chat (reads issues; never edits PDF directly)
```

重要实现原则：

- 每个 PDF 在独立进程或容器中处理；设置文件大小、页数、像素、CPU、内存和超时限制。PyMuPDF 官方明确说明不支持多线程并可能崩溃，适合多进程 worker，而不是共享线程池。[PyMuPDF multiprocessing](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html)
- 原文件不可覆盖；所有修复生成派生版本，并记录命令、版本、ICC 哈希和规则 ID。
- 规则输出必须包含 `severity`、`evidence`、`confidence`、`fix.mode`、`fix.safety`。
- 将产品 SKU/印厂要求做成 Print Preset。没有目标印刷条件，就没有唯一正确的 CMYK 或 PDF/X。
- 修复后必须重新解析、独立渲染、做结构检查和视觉差异检查。
- GPT/LLM 只负责解释、建议、QA 编排和对话；不直接修改内容流或决定无预览的高风险修复。

## 6. 风险清单

| 风险 | 等级 | 缓解措施 |
|---|---|---|
| AGPL/商业许可 | 高 | PRD 前完成 Artifex/替代引擎法律与成本评估 |
| PDF/X“声明即合规”的假阳性 | 高 | 接入独立 validator、合规测试集和印厂验收 |
| 错误 ICC/印刷条件导致色差 | 高 | Print Preset、ICC 版本化、软打样、审批 |
| 字体替代导致版式变化 | 高 | 禁止静默替代；精确字体校验 + render diff |
| 出血生成破坏主体/文字 | 高 | 只对白名单场景自动；其余预览确认 |
| AI 超分制造伪细节 | 中高 | 保留原 DPI 与来源；标为增强而非恢复 |
| 恶意/畸形 PDF | 高 | 隔离进程、资源限制、多解析器交叉检查 |
| 复杂专色、透明、叠印 | 高 | 专业规则包、RIP/打样、先不承诺全自动 |
| “万能 UDF”过度设计 | 中 | 第一阶段只定义 PDF Preflight UDF |

## 7. 建议的 MVP 边界与验收门槛

### MVP 应包含

- PDF 上传、病毒/配额/超时保护。
- 页面框、图片 DPI、字体嵌入、颜色空间、透明/专色基础检测。
- 版本化规则和可解释 issue report。
- 明确成品尺寸后的页面框与裁切标记。
- 均匀纯色背景出血。
- 指定 Print Preset 后的 CMYK/PDF/X 候选输出。
- 修复前后预览、审计日志、人工确认节点。

### MVP 不应承诺

- Figma/Canva/Affinity 原文件重建。
- 任意场景自动出血。
- 低 DPI 图片必然可修复到“真实 300 DPI”。
- 所有字体无差异自动嵌入/转曲。
- 未经独立验证与印厂测试的“100% 可印”。

### 进入 Alpha 的硬门槛

1. 至少建立 200-500 份匿名化真实 PDF 回归集，覆盖设计工具、字体、透明、专色和破损文件。
2. 每条规则有正例、负例、误报率、漏报率和人工裁决标准。
3. 修复后 100% 重跑解析、语法检查、渲染 diff；高风险规则必须人工确认。
4. 选定至少 2 个印厂/产品规格，固定成品尺寸、出血、PDF/X 与 ICC。
5. PDF/X 使用独立验证器或商业预检工具复核，不能只检查元数据。
6. 完成 AGPL/商业许可决策。

## 8. 最终建议

项目可以进入下一阶段，但应先做一个 **6-8 周 PDF Preflight Alpha**，而不是立即编写覆盖所有设计格式的 60-80 页 PRD。Alpha 的目标不是增加更多“AI 功能”，而是完成三件事：真实文件回归集、Print Preset/规则体系、以及商业许可与独立合规验证闭环。

建议的产品承诺是：

> 我们自动发现印前问题；只在高置信度、可回滚的场景自动修复；其余问题给出证据、预览和明确的人工决策。

这条路线技术上可落地，也更符合印刷生产对可审计、可复现和风险可控的要求。

## 9. POC 产物索引

- `output/poc/input-analysis.json`：输入 UDF/解析结果。
- `output/poc/input-preflight.json`：输入规则结果。
- `output/poc/final-analysis.json`：输出解析结果。
- `output/poc/final-preflight.json`：输出规则结果。
- `output/poc/verification.json`：版本、断言、qpdf、视觉差异和修复命令证据。
- `output/poc/rendered/final-poppler.png`：Poppler 交叉渲染。
- `output/pdf/poc-fixed-pdfx4.pdf`：最终 PDF/X-4 候选文件。
