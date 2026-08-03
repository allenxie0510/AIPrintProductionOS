"use client";

import { ChangeEvent, DragEvent, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Issue = {
  code: string;
  ruleVersion: string;
  severity: "FAIL" | "WARN" | "INFO";
  confidence: number;
  page: number | null;
  message: string;
  evidence: Record<string, unknown> | unknown[] | null;
  fix: { mode: string; safety: "auto" | "confirm" | "manual" };
};

type Report = {
  analysis: { source: { pageCount: number; bytes: number }; pages: unknown[] };
  preflight: { productionScore: number; status: string; issues: Issue[] };
  afterPreflight?: { productionScore: number; status: string; issues: Issue[] };
  validation?: { syntaxPassed: boolean; validator: string; pdfxState: string } | null;
};

type Job = {
  jobId: string;
  accessToken: string;
  fileName: string;
  presetId: string;
  status: string;
  expiresAt: string;
  downloadAvailable: boolean;
  report?: Report;
};

const presets = [
  { id: "designer-standard-poc", label: "名片 / 宣传单", meta: "300 PPI · 3 mm 出血" },
  { id: "poster-poc", label: "海报", meta: "150 PPI · 3 mm 出血" },
  { id: "large-format-poc", label: "大幅喷绘", meta: "120 PPI · 5 mm 出血" },
];

const issueNames: Record<string, string> = {
  "COLOR.RGB_USED": "包含 RGB 对象",
  "FONT.NOT_EMBEDDED": "字体未嵌入",
  "IMAGE.LOW_EFFECTIVE_DPI": "图片有效分辨率不足",
  "PAGE.TRIMBOX_MISSING": "缺少明确裁切框",
  "PAGE.BLEED_INSUFFICIENT": "出血不足",
  "PDFX.NOT_DECLARED": "缺少 PDF/X 输出条件",
  "PDF.ENCRYPTED": "PDF 已加密",
};

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ErrorBanner({ message }: { message: string }) {
  return <div className="error-banner" role="alert">{message}</div>;
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [presetId, setPresetId] = useState(presets[0].id);
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [bleedFix, setBleedFix] = useState(true);
  const [pdfxFix, setPdfxFix] = useState(true);
  const [fontAck, setFontAck] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);

  const activePreflight = report?.afterPreflight ?? report?.preflight;
  const issues = activePreflight?.issues ?? [];
  const hasFontIssue = issues.some((item) => item.code === "FONT.NOT_EMBEDDED");
  const hasBleedIssue = issues.some((item) => item.code === "PAGE.BLEED_INSUFFICIENT");
  const phase = !job ? "upload" : report?.afterPreflight ? "result" : "diagnosis";
  const selectedPreset = useMemo(() => presets.find((item) => item.id === presetId)!, [presetId]);

  function chooseFile(next: File | null) {
    setError("");
    if (!next) return;
    if (next.type !== "application/pdf" && !next.name.toLowerCase().endsWith(".pdf")) {
      setError("请选择 PDF 文件。图片可以稍后作为低分辨率对象的替换素材上传。");
      return;
    }
    if (next.size > 100 * 1024 * 1024) {
      setError("当前 MVP 单个 PDF 上限为 100 MB。");
      return;
    }
    setFile(next);
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragging(false);
    chooseFile(event.dataTransfer.files[0] ?? null);
  }

  async function analyze() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("presetId", presetId);
      const response = await fetch(`${API_BASE}/v1/jobs`, { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "诊断失败，请检查文件后重试。");
      const created = payload as Job;
      let createdReport: Report | null = null;
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const statusResponse = await fetch(`${API_BASE}/v1/jobs/${created.jobId}`, {
          headers: { "X-Job-Token": created.accessToken },
        });
        const statusPayload = await statusResponse.json();
        if (statusPayload.status === "failed") throw new Error(statusPayload.error?.message ?? "报告生成失败。");
        if (statusPayload.status === "awaiting_decision") {
          const reportResponse = await fetch(`${API_BASE}/v1/jobs/${created.jobId}/report`, {
            headers: { "X-Job-Token": created.accessToken },
          });
          if (reportResponse.ok) createdReport = await reportResponse.json();
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      if (!createdReport) throw new Error("诊断超时。任务仍会按生命周期自动清理，请稍后重新上传。");
      setJob(created);
      setReport(createdReport);
      setBleedFix(createdReport.preflight.issues.some((item: Issue) => item.code === "PAGE.BLEED_INSUFFICIENT"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "诊断失败。");
    } finally {
      setBusy(false);
    }
  }

  async function applyFixes() {
    if (!job) return;
    const actions = [bleedFix && "bleed_and_crop", pdfxFix && "pdfx_candidate"].filter(Boolean);
    if (!actions.length) {
      setError("请至少选择一项修复，或保留当前诊断报告。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Job-Token": job.accessToken },
        body: JSON.stringify({ actions, acknowledgeFontSubstitution: fontAck }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error?.message ?? "修复执行失败。");
      setJob((current) => current ? { ...current, ...payload } : current);
      setReport(payload.report);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "修复执行失败。");
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/download`, {
        headers: { "X-Job-Token": job.accessToken },
      });
      if (!response.ok) {
        const payload = await response.json();
        throw new Error(payload.error?.message ?? "文件尚不可下载。");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${job.fileName.replace(/\.pdf$/i, "")}-print-ready-candidate.pdf`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "下载失败。");
    } finally {
      setBusy(false);
    }
  }

  async function deleteFiles() {
    if (!job) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/artifacts`, {
        method: "DELETE",
        headers: { "X-Job-Token": job.accessToken },
      });
      if (!response.ok) throw new Error("文件删除失败，请稍后重试。系统仍会按到期时间自动清理。");
      setJob(null);
      setReport(null);
      setFile(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "文件删除失败。");
    } finally {
      setBusy(false);
    }
  }

  async function sendFeedback(rating: "accepted" | "incorrect") {
    if (!job) return;
    await fetch(`${API_BASE}/v1/jobs/${job.jobId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Job-Token": job.accessToken },
      body: JSON.stringify({ rating, printerOutcome: "unknown" }),
    });
    setFeedbackSent(true);
  }

  function downloadReport() {
    if (!report || !job) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${job.fileName.replace(/\.pdf$/i, "")}-preflight-report.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function restart() {
    if (job) {
      try {
        await fetch(`${API_BASE}/v1/jobs/${job.jobId}/artifacts`, {
          method: "DELETE",
          headers: { "X-Job-Token": job.accessToken },
        });
      } catch {
        // The server-side TTL remains the fallback when the browser is offline.
      }
    }
    setJob(null);
    setReport(null);
    setFile(null);
    setError("");
    setFeedbackSent(false);
    setFontAck(false);
  }

  return (
    <main>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AI Print Production OS 首页">
          <span className="brand-mark">P</span>
          <span>PrintReady <em>AI</em></span>
        </a>
        <div className="security-note"><span className="pulse" /> 文件默认 24 小时后删除</div>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <p className="eyebrow">DESIGNER-FIRST PDF PREFLIGHT</p>
          <h1>交付印厂之前，<br />先让文件<span>说真话。</span></h1>
          <p className="lede">在线检查出血、有效分辨率、颜色、字体与 PDF/X 风险。能安全修的自动处理，不能安全修的明确告诉你原因。</p>
          <div className="promise-row">
            <span>不伪造 300 PPI</span><span>不静默替换字体</span><span>不永久保存文件</span>
          </div>
        </div>

        <div className="workspace">
          <div className="steps" aria-label="处理进度">
            {["上传", "诊断", "修复", "交付"].map((label, index) => {
              const active = phase === "upload" ? 0 : phase === "diagnosis" ? 1 : 3;
              return <div className={index <= active ? "step active" : "step"} key={label}><b>{index + 1}</b><span>{label}</span></div>;
            })}
          </div>

          {error && <ErrorBanner message={error} />}

          {phase === "upload" && (
            <div className="upload-panel">
              <label
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={onDrop}
              >
                <input type="file" accept="application/pdf,.pdf" onChange={(event: ChangeEvent<HTMLInputElement>) => chooseFile(event.target.files?.[0] ?? null)} />
                <span className="upload-icon">PDF</span>
                {file ? <><strong>{file.name}</strong><small>{formatBytes(file.size)} · 点击可重新选择</small></> : <><strong>拖入待交付的 PDF</strong><small>或点击选择文件 · 最大 100 MB / 20 页</small></>}
              </label>

              <div className="preset-title"><span>目标产品</span><small>规则会根据实际印刷尺寸变化</small></div>
              <div className="preset-grid">
                {presets.map((preset) => (
                  <button type="button" key={preset.id} className={preset.id === presetId ? "preset selected" : "preset"} onClick={() => setPresetId(preset.id)}>
                    <strong>{preset.label}</strong><small>{preset.meta}</small>
                  </button>
                ))}
              </div>
              <button className="primary" disabled={!file || busy} onClick={analyze}>{busy ? "正在解析真实 PDF 对象…" : "开始印前诊断"}<span>→</span></button>
              <p className="fineprint">上传即创建临时任务。源文件不可覆盖，下载后可立即删除。</p>
            </div>
          )}

          {phase === "diagnosis" && report && job && (
            <div className="diagnosis-panel">
              <div className="score-row">
                <div className="score"><span>{report.preflight.productionScore}</span><small>印前准备度</small></div>
                <div><p className="eyebrow">诊断完成</p><h2>{job.fileName}</h2><p>{report.analysis.source.pageCount} 页 · {formatBytes(report.analysis.source.bytes)} · {selectedPreset.label}</p></div>
              </div>
              <div className="issue-list">
                {report.preflight.issues.map((issue) => (
                  <article className="issue" key={`${issue.code}-${issue.page ?? 0}-${JSON.stringify(issue.evidence)}`}>
                    <span className={`severity ${issue.severity.toLowerCase()}`}>{issue.severity}</span>
                    <div><h3>{issueNames[issue.code] ?? issue.code}</h3><p>{issue.message}</p><small>规则 {issue.ruleVersion} · {Math.round(issue.confidence * 100)}% 置信度 · {issue.fix.safety}</small></div>
                  </article>
                ))}
              </div>
              <div className="fix-plan">
                <h3>修复计划</h3>
                {hasBleedIssue && <label><input type="checkbox" checked={bleedFix} onChange={(event) => setBleedFix(event.target.checked)} /><span><strong>扩展安全背景并添加裁切标记</strong><small>仅当页面边缘分类为均匀纯色时执行</small></span></label>}
                <label><input type="checkbox" checked={pdfxFix} onChange={(event) => setPdfxFix(event.target.checked)} /><span><strong>生成 CMYK / PDF/X-4 候选</strong><small>使用目标 ICC；独立验证前仍标记为 Candidate</small></span></label>
                {pdfxFix && hasFontIssue && <label className="warning-choice"><input type="checkbox" checked={fontAck} onChange={(event) => setFontAck(event.target.checked)} /><span><strong>我确认本次候选导出可能使用替代字体</strong><small>当前缺少原字体。结果必须放大检查，不会被标记为无风险。</small></span></label>}
              </div>
              <button className="primary" disabled={busy || (pdfxFix && hasFontIssue && !fontAck)} onClick={applyFixes}>{busy ? "正在生成派生文件并复检…" : "执行已确认的修复"}<span>→</span></button>
              <button className="text-button" onClick={restart}>删除当前文件并换一个</button>
            </div>
          )}

          {phase === "result" && report && job && activePreflight && (
            <div className="result-panel">
              <div className="result-head">
                <div className={activePreflight.status === "FAIL" ? "result-icon partial" : "result-icon"}>{activePreflight.status === "FAIL" ? "!" : "✓"}</div>
                <div><p className="eyebrow">复检完成</p><h2>{activePreflight.status === "FAIL" ? "已生成候选文件，仍有风险" : "候选文件已准备"}</h2><p>所有已执行修复都已重新解析；剩余问题不会被隐藏。</p></div>
              </div>
              <div className="comparison">
                <div><small>修复前</small><strong>{report.preflight.productionScore}</strong></div><span>→</span><div><small>修复后</small><strong>{activePreflight.productionScore}</strong></div>
                <div className="validation"><small>结构验证</small><strong>{report.validation?.syntaxPassed ? "PASS" : "未通过"}</strong><em>PDF/X 候选 · 尚未独立认证</em></div>
              </div>
              {issues.length > 0 && <div className="remaining"><strong>仍需关注</strong>{issues.map((issue) => <span key={`${issue.code}-${issue.page ?? 0}`}>{issueNames[issue.code] ?? issue.code}</span>)}</div>}
              <button className="primary" disabled={busy} onClick={download}>下载印刷候选 PDF<span>↓</span></button>
              <div className="result-actions"><button onClick={downloadReport}>下载诊断 JSON</button><button onClick={deleteFiles}>立即删除所有文件</button><button onClick={restart}>处理下一个 PDF</button></div>
              <div className="feedback">{feedbackSent ? <span>感谢，你的反馈已与本次规则结果关联。</span> : <><span>这次结果是否符合预期？</span><button onClick={() => sendFeedback("accepted")}>符合</button><button onClick={() => sendFeedback("incorrect")}>不符合</button></>}</div>
            </div>
          )}
        </div>
      </section>

      <section className="trust-strip">
        <div><strong>Effective PPI</strong><span>按像素和实际落版尺寸计算</span></div>
        <div><strong>Evidence first</strong><span>每个判断都有页面、对象或测量证据</span></div>
        <div><strong>Human authority</strong><span>高风险修复必须由设计师确认</span></div>
      </section>
      <footer><span>AI Print Production OS · Alpha MVP</span><span>候选文件不能替代印厂打样与最终验收</span></footer>
    </main>
  );
}
