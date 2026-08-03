# AI Print Production OS

[![PDF Preflight POC](https://github.com/allenxie0510/AIPrintProductionOS/actions/workflows/poc-ci.yml/badge.svg)](https://github.com/allenxie0510/AIPrintProductionOS/actions/workflows/poc-ci.yml)

PDF-first 的 AI 印前分析与生产操作系统。第一阶段目标不是重建 Figma/Canva，而是把 PDF 预检、风险分级、受控修复和可审计输出做到可靠。

本仓库按 [GNU Affero General Public License v3.0](LICENSE) 发布。线上服务用户可以在本仓库取得对应源码；第三方引擎说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

当前状态：**本地 Web MVP 已完成，公开 AGPL 在线演示正在部署；专有生产部署仍受商业许可、隔离和独立 PDF/X 验证 Gate 约束。**

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
# Linux/CI: set PRINT_POC_CMYK_PROFILE when the profile is not in a standard path
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

## 运行 Web MVP

后端：

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/uvicorn print_preflight.api:app --reload --host 127.0.0.1 --port 8000
```

前端（另一个终端）：

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

打开前端显示的本地地址。API 文档位于 `http://127.0.0.1:8000/docs`。

MVP 已包含：

- PDF 上传、签名/大小/页数检查和匿名任务访问令牌。
- 任务状态、版本化 Print Preset、规则证据和准备度评分。
- 纯色出血/裁切标记以及经明确确认的 PDF/X-4 候选输出。
- 修复后重新分析、qpdf 结构验证、下载和立即删除。
- SQLite 结构化元数据、反馈和到期文件清理。
- 响应式设计师 Web 界面。

清理过期任务：

```bash
.venv/bin/python scripts/cleanup_jobs.py
```

生产环境必须把应用内后台任务替换为持久队列，并使用对象存储、容器隔离、恶意文件扫描、限流和独立 PDF/X 验证器。

## 部署在线演示

仓库根目录的 `Dockerfile` 固定并校验 Ghostscript 10.07.1，`render.yaml` 提供新加坡区域的单实例 Render 演示服务。完整步骤和限制见 [`docs/08-operations/deployment.md`](docs/08-operations/deployment.md)。
