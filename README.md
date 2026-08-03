# AI Print Production OS

PDF-first 的 AI 印前分析与生产操作系统。第一阶段目标不是重建 Figma/Canva，而是把 PDF 预检、风险分级、受控修复和可审计输出做到可靠。

当前状态：**PDF Preflight POC 已验证，准备进入 Alpha 规划。**

## 从这里开始

所有开发者和 AI Agent 按以下顺序读取：

1. [`PROJECT.md`](PROJECT.md) - 目标、状态、架构和当前 Sprint。
2. [`docs/00-project/constitution.md`](docs/00-project/constitution.md) - 不可随意破坏的工程原则。
3. [`docs/README.md`](docs/README.md) - 规范与决策索引。
4. [`AGENTS.md`](AGENTS.md) - 仓库内 AI/工程协作规则。

## 已验证的 POC

POC 验证了：

- PDF 页面框、图片、有效 DPI、字体、颜色空间和 PDF/X 元数据解析。
- 规则驱动的 PASS/WARN/FAIL 与 Production Score。
- 均匀纯色背景的 3 mm 出血、TrimBox 和裁切标记生成。
- ICC 驱动的 RGB -> CMYK、字体嵌入和 PDF/X-4 候选输出。
- qpdf 结构检查、双渲染器视觉回归和可复现测试。

详细结论见 [`docs/05-testing/technical-feasibility-report.md`](docs/05-testing/technical-feasibility-report.md)。

## 运行 POC

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
# macOS POC system tools: brew install ghostscript qpdf little-cms2
.venv/bin/python scripts/run_poc.py
.venv/bin/python -m unittest discover -s tests -v
```

主要输出：

- `output/poc/input-analysis.json`
- `output/poc/input-preflight.json`
- `output/poc/final-analysis.json`
- `output/poc/final-preflight.json`
- `output/poc/verification.json`
- `output/pdf/poc-fixed-pdfx4.pdf`

POC 输出不构成印厂验收或 PDF/X 独立合规认证。
