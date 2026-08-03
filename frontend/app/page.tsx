"use client";

/* eslint-disable @next/next/no-img-element -- authenticated blob previews cannot use the image optimizer */

import { ChangeEvent, DragEvent, useEffect, useMemo, useState } from "react";

const DEFAULT_PRODUCTION_API_BASE = "https://ai-print-production-os-api.onrender.com";
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL?.trim() || DEFAULT_PRODUCTION_API_BASE)
  .replace(/\/+$/, "");

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
  fixPlan: FixAction[];
  previews?: {
    source?: { available: boolean; page: number; width?: number; height?: number };
    current?: { available: boolean; page: number; width?: number; height?: number };
  };
  fix?: {
    actions?: string[];
    summary?: string[];
    resolvedIssues?: Issue[];
    history?: Array<{ actions: string[]; summary?: string[]; resolvedIssues?: Issue[] }>;
  } | null;
  providedFonts?: Array<{ expectedName: string; fontName: string; ready: boolean }>;
  validation?: { syntaxPassed: boolean; validator: string; pdfxState: string } | null;
};

type FixAction = {
  action: "bleed_and_crop" | "trim_and_crop_marks" | "pdfx_candidate";
  label: string;
  applicable: boolean;
  executable: boolean;
  safety: "auto" | "confirm" | "manual";
  reason: string;
  requiresFontAcknowledgement?: boolean;
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

type ApiError = { code?: string; message?: string };
type JsonPayload = { error?: ApiError; status?: string; [key: string]: unknown };

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

const apiErrorMessages: Record<string, string> = {
  ENGINE_RESOURCE_LIMIT: "这个 PDF 的结构或图片复杂度超过当前在线安全处理上限。请从设计工具重新导出为优化 PDF，或缩小页面/图片后重试。",
  ENGINE_TIMEOUT: "这个 PDF 的处理时间超过在线安全上限。请从设计工具重新导出为优化 PDF 后重试。",
  PDF_COMPLEXITY_LIMIT_EXCEEDED: "这个 PDF 超过当前在线安全复杂度限制。请减少页面、对象或超大图片后重试。",
  ENGINE_PROCESS_FAILED: "PDF 引擎已安全终止，没有影响在线服务。请重新导出 PDF 后重试。",
  FIX_ACTION_UNSAFE: "所选修复不满足安全执行条件，文件没有被修改。请按修复计划选择可执行动作。",
  FIX_QUALITY_REGRESSION: "本次转换会新增更低分辨率的栅格对象，因此已停止并保留上一版本。请从设计软件按正确页面尺寸重新导出，或向印厂索取目标预设。",
  REPLACEMENT_IMAGE_TOO_SMALL: "这张替换图片仍然不够大。请选择像素尺寸更高的原图。",
  IMAGE_FORMAT_UNSUPPORTED: "请上传 PNG、JPEG、TIFF 或 WebP 图片。",
  FONT_NAME_MISMATCH: "字体名称与 PDF 请求的字体不一致。请上传原字体文件，或明确选择替代字体导出。",
  FONT_FORMAT_UNSUPPORTED: "请上传单个 TTF 或 OTF 字体文件。",
};

function issueEvidence(issue: Issue) {
  return issue.evidence && !Array.isArray(issue.evidence) ? issue.evidence : {};
}

function issueKey(issue: Issue) {
  const evidence = issueEvidence(issue);
  return [issue.code, issue.page ?? 0, evidence.xref ?? "", issue.message].join(":");
}

function fontNameFromIssue(issue: Issue) {
  return issue.message.split(": ", 2)[1] || issue.message;
}

function normalizedFontName(value: string) {
  return value.replace(/^[A-Z]{6}\+/, "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

function sameIssue(left: Issue, right: Issue) {
  if (left.code !== right.code || left.page !== right.page) return false;
  const leftEvidence = issueEvidence(left);
  const rightEvidence = issueEvidence(right);
  if (left.code === "IMAGE.LOW_EFFECTIVE_DPI") {
    return leftEvidence.xref === rightEvidence.xref;
  }
  return left.message === right.message || left.code === right.code;
}

const resolvedDescriptions: Record<string, string> = {
  "PAGE.TRIMBOX_MISSING": "已写入明确裁切框，并在外围工作区添加裁切标记。",
  "PAGE.BLEED_INSUFFICIENT": "已补足可安全延展的纯色出血，并重新检查页面边缘。",
  "COLOR.RGB_USED": "已按目标 ICC 转换颜色并生成 CMYK 候选文件。",
  "PDFX.NOT_DECLARED": "已生成 PDF/X-4 候选和 OutputIntent，仍需印厂最终验证。",
  "FONT.NOT_EMBEDDED": "字体已在候选文件中嵌入；请用左侧预览确认字形与换行。",
  "IMAGE.LOW_EFFECTIVE_DPI": "已原位替换高分辨率图片，并按实际落版尺寸重新计算 PPI。",
};

function apiErrorMessage(error: ApiError | undefined, fallback: string) {
  if (error?.code && apiErrorMessages[error.code]) return apiErrorMessages[error.code];
  return error?.message ?? fallback;
}

async function jsonPayload(response: Response): Promise<JsonPayload> {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function fetchTransient(input: RequestInfo | URL, init?: RequestInit, attempts = 5) {
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const response = await fetch(input, init);
      if (![502, 503, 504].includes(response.status) || attempt === attempts - 1) return response;
    } catch (cause) {
      lastError = cause;
      if (attempt === attempts - 1) throw cause;
    }
    await new Promise((resolve) => window.setTimeout(resolve, Math.min(1000 * 2 ** attempt, 8000)));
  }
  throw lastError instanceof Error ? lastError : new Error("在线处理服务暂时不可用。");
}

function BeforeAfterComparison({ before, after, position, onChange }: {
  before: string;
  after: string;
  position: number;
  onChange: (position: number) => void;
}) {
  return (
    <div className="preview-card">
      <div className="preview-heading"><span>修复前</span><span>拖动查看差异</span><span>修复后</span></div>
      <div className="compare-frame">
        <img src={before} alt="修复前 PDF 第一页" />
        <img className="after-image" src={after} alt="修复后 PDF 第一页" style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }} />
        <div className="compare-divider" style={{ left: `${position}%` }} aria-hidden="true"><span>↔</span></div>
        <input className="compare-range" type="range" min="0" max="100" value={position} onChange={(event) => onChange(Number(event.target.value))} aria-label="拖动比较修复前后效果" />
      </div>
      <p className="preview-note">第一页渲染预览 · 最终交付以下载的 PDF 和复检报告为准</p>
    </div>
  );
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [presetId, setPresetId] = useState(presets[0].id);
  const [job, setJob] = useState<Job | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [fixingIssue, setFixingIssue] = useState("");
  const [fontConsent, setFontConsent] = useState<Record<string, boolean>>({});
  const [lastSuccess, setLastSuccess] = useState("");
  const [deliveryMode, setDeliveryMode] = useState(false);
  const [compareMode, setCompareMode] = useState(false);
  const [feedbackSent, setFeedbackSent] = useState(false);
  const [sourcePreviewUrl, setSourcePreviewUrl] = useState("");
  const [fixedPreviewUrl, setFixedPreviewUrl] = useState("");
  const [comparePosition, setComparePosition] = useState(50);

  const activePreflight = report?.afterPreflight ?? report?.preflight;
  const issues = activePreflight?.issues ?? [];
  const hasRepairs = Boolean(report?.afterPreflight);
  const resolvedIssues = (report?.fix?.history ?? []).flatMap((event) => event.resolvedIssues ?? []);
  const resolvedIssueKeys = new Set(resolvedIssues.map(issueKey));
  const displayedIssues = hasRepairs
    ? [...resolvedIssues.filter((issue, index, all) => all.findIndex((item) => issueKey(item) === issueKey(issue)) === index), ...issues]
    : issues;
  const phase = !job ? "upload" : deliveryMode ? "result" : hasRepairs ? "repair" : "diagnosis";
  const selectedPreset = useMemo(() => presets.find((item) => item.id === presetId)!, [presetId]);
  const localPdfUrl = useMemo(() => file ? URL.createObjectURL(file) : "", [file]);
  const fixPlan = report?.fixPlan ?? [];
  const bleedAction = fixPlan.find((item) => item.action === "bleed_and_crop");
  const trimAction = fixPlan.find((item) => item.action === "trim_and_crop_marks");
  const pdfxAction = fixPlan.find((item) => item.action === "pdfx_candidate");

  useEffect(() => () => { if (localPdfUrl) URL.revokeObjectURL(localPdfUrl); }, [localPdfUrl]);
  useEffect(() => () => { if (sourcePreviewUrl) URL.revokeObjectURL(sourcePreviewUrl); }, [sourcePreviewUrl]);
  useEffect(() => () => { if (fixedPreviewUrl) URL.revokeObjectURL(fixedPreviewUrl); }, [fixedPreviewUrl]);

  async function loadPreview(targetJob: Job, stage: "source" | "current") {
    const response = await fetchTransient(
      `${API_BASE}/v1/jobs/${targetJob.jobId}/preview?stage=${stage}&page=1`,
      { headers: { "X-Job-Token": targetJob.accessToken } },
    );
    if (!response.ok) return;
    const url = URL.createObjectURL(await response.blob());
    if (stage === "source") setSourcePreviewUrl(url);
    else setFixedPreviewUrl(url);
  }

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
    setSourcePreviewUrl("");
    setFixedPreviewUrl("");
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
      const health = await fetchTransient(`${API_BASE}/health`, undefined, 6);
      if (!health.ok) throw new Error("在线处理服务仍在启动，请稍后再试。");
      const body = new FormData();
      body.append("file", file);
      body.append("presetId", presetId);
      const response = await fetch(`${API_BASE}/v1/jobs`, { method: "POST", body });
      const payload = await jsonPayload(response);
      if (!response.ok) throw new Error(apiErrorMessage(payload.error, "诊断失败，请检查文件后重试。"));
      const created = payload as unknown as Job;
      let createdReport: Report | null = null;
      for (let attempt = 0; attempt < 90; attempt += 1) {
        const statusResponse = await fetchTransient(`${API_BASE}/v1/jobs/${created.jobId}`, {
          headers: { "X-Job-Token": created.accessToken },
        });
        const statusPayload = await jsonPayload(statusResponse);
        if (!statusResponse.ok) {
          throw new Error(apiErrorMessage(statusPayload.error, "任务状态读取失败，请重新上传。"));
        }
        if (statusPayload.status === "failed") {
          throw new Error(apiErrorMessage(statusPayload.error, "报告生成失败。"));
        }
        if (statusPayload.status === "awaiting_decision") {
          const reportResponse = await fetchTransient(`${API_BASE}/v1/jobs/${created.jobId}/report`, {
            headers: { "X-Job-Token": created.accessToken },
          });
          if (!reportResponse.ok) {
            const reportError = await jsonPayload(reportResponse);
            throw new Error(apiErrorMessage(reportError.error, "诊断报告读取失败，请重新上传。"));
          }
          createdReport = await reportResponse.json();
          break;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      if (!createdReport) throw new Error("诊断超时。任务仍会按生命周期自动清理，请稍后重新上传。");
      setJob(created);
      setReport(createdReport);
      await loadPreview(created, "source");
    } catch (cause) {
      setError(cause instanceof TypeError
        ? "无法连接在线处理服务。Render 可能正在冷启动或恢复，请等待约一分钟后重试。"
        : cause instanceof Error ? cause.message : "诊断失败。");
    } finally {
      setBusy(false);
    }
  }

  async function applySingleFix(action: FixAction["action"], key: string, acknowledgeFontSubstitution = false) {
    if (!job) return;
    setBusy(true);
    setFixingIssue(key);
    setError("");
    setLastSuccess("");
    try {
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/fix`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Job-Token": job.accessToken },
        body: JSON.stringify({ actions: [action], acknowledgeFontSubstitution }),
      });
      const payload = await jsonPayload(response);
      if (!response.ok) throw new Error(apiErrorMessage(payload.error, "修复执行失败。"));
      setJob((current) => current ? { ...current, ...payload } : current);
      const nextReport = payload.report as Report;
      setReport(nextReport);
      setLastSuccess(nextReport.fix?.summary?.join(" ") || "此项已完成并重新检查。 ");
      await loadPreview(job, "current");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "修复执行失败。");
    } finally {
      setBusy(false);
      setFixingIssue("");
    }
  }

  async function replaceImage(issue: Issue, replacement: File | null) {
    if (!job || !replacement) return;
    const evidence = issueEvidence(issue);
    const key = issueKey(issue);
    setBusy(true);
    setFixingIssue(key);
    setError("");
    setLastSuccess("");
    try {
      const body = new FormData();
      body.append("file", replacement);
      body.append("xref", String(evidence.xref));
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/assets/image-replacement`, {
        method: "POST",
        headers: { "X-Job-Token": job.accessToken },
        body,
      });
      const payload = await jsonPayload(response);
      if (!response.ok) throw new Error(apiErrorMessage(payload.error, "图片替换失败。"));
      setJob((current) => current ? { ...current, ...payload } : current);
      const nextReport = payload.report as Report;
      setReport(nextReport);
      setLastSuccess(nextReport.fix?.summary?.join(" ") || "图片已替换并重新检查有效 PPI。");
      await loadPreview(job, "current");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "图片替换失败。");
    } finally {
      setBusy(false);
      setFixingIssue("");
    }
  }

  async function uploadFont(issue: Issue, fontFile: File | null) {
    if (!job || !fontFile) return;
    const key = issueKey(issue);
    const expectedName = fontNameFromIssue(issue);
    setBusy(true);
    setFixingIssue(key);
    setError("");
    setLastSuccess("");
    try {
      const body = new FormData();
      body.append("file", fontFile);
      body.append("expectedName", expectedName);
      const response = await fetch(`${API_BASE}/v1/jobs/${job.jobId}/assets/font`, {
        method: "POST",
        headers: { "X-Job-Token": job.accessToken },
        body,
      });
      const payload = await jsonPayload(response);
      if (!response.ok) throw new Error(apiErrorMessage(payload.error, "字体上传失败。"));
      setReport(payload.report as Report);
      setLastSuccess(`原字体 ${expectedName} 已验证，执行 PDF/X 转换时会优先使用它。`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "字体上传失败。");
    } finally {
      setBusy(false);
      setFixingIssue("");
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
      setSourcePreviewUrl("");
      setFixedPreviewUrl("");
      setFontConsent({});
      setFixingIssue("");
      setLastSuccess("");
      setDeliveryMode(false);
      setCompareMode(false);
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
    setFontConsent({});
    setFixingIssue("");
    setLastSuccess("");
    setDeliveryMode(false);
    setCompareMode(false);
    setSourcePreviewUrl("");
    setFixedPreviewUrl("");
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
          {!file ? <>
            <p className="eyebrow">DESIGNER-FIRST PDF PREFLIGHT</p>
            <h1>交付印厂之前，<br />先让文件<span>说真话。</span></h1>
            <p className="lede">在线检查出血、有效分辨率、颜色、字体与 PDF/X 风险。能安全修的自动处理，不能安全修的明确告诉你原因。</p>
            <div className="promise-row">
              <span>不伪造 300 PPI</span><span>不静默替换字体</span><span>不永久保存文件</span>
            </div>
          </> : report?.afterPreflight && sourcePreviewUrl && fixedPreviewUrl && compareMode ? (
            <div>
              <BeforeAfterComparison before={sourcePreviewUrl} after={fixedPreviewUrl} position={comparePosition} onChange={setComparePosition} />
              <button className="preview-toggle" onClick={() => setCompareMode(false)}>返回当前修复版</button>
            </div>
          ) : (
            <div className="preview-card">
              <div className="preview-heading">
                <span>{fixedPreviewUrl ? "当前修复版本" : report ? "原始文件" : "待诊断文件"}</span>
                {fixedPreviewUrl && sourcePreviewUrl ? <button onClick={() => setCompareMode(true)}>对比原稿</button> : <span>第 1 页</span>}
              </div>
              <div className="pdf-frame">
                {fixedPreviewUrl || sourcePreviewUrl
                  ? <img src={fixedPreviewUrl || sourcePreviewUrl} alt="当前 PDF 第一页实际预览" />
                  : <object data={localPdfUrl} type="application/pdf" aria-label="上传 PDF 预览"><p>浏览器无法显示 PDF 预览。</p></object>}
                {busy && <div className="preview-processing"><span />正在隔离解析 PDF…</div>}
              </div>
              <p className="preview-note">{file.name} · {formatBytes(file.size)}</p>
            </div>
          )}
        </div>

        <div className="workspace">
          <div className="steps" aria-label="处理进度">
            {["上传", "诊断", "修复", "交付"].map((label, index) => {
              const active = phase === "upload" ? 0 : phase === "diagnosis" ? 1 : phase === "repair" ? 2 : 3;
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

          {(phase === "diagnosis" || phase === "repair") && report && job && (
            <div className="diagnosis-panel">
              <div className="score-row">
                <div className="score"><span>{activePreflight?.productionScore ?? report.preflight.productionScore}</span><small>印前准备度</small></div>
                <div><p className="eyebrow">{hasRepairs ? "逐项修复" : "诊断完成"}</p><h2>{job.fileName}</h2><p>{report.analysis.source.pageCount} 页 · {formatBytes(report.analysis.source.bytes)} · {selectedPreset.label}</p></div>
              </div>
              {lastSuccess && <div className="success-banner" role="status"><b>✓</b><span><strong>修复完成</strong>{lastSuccess}</span></div>}
              <div className="repair-intro"><strong>按问题逐项处理</strong><span>每次只修改一个目标，完成后立即复检并更新左侧实际预览。</span></div>
              <div className="issue-list repair-list">
                {displayedIssues.map((issue) => {
                  const key = issueKey(issue);
                  const resolved = resolvedIssueKeys.has(key) && !issues.some((current) => sameIssue(issue, current));
                  const evidence = issueEvidence(issue);
                  const isWorking = fixingIssue === key;
                  const fontName = fontNameFromIssue(issue);
                  const exactFontReady = Boolean(report.providedFonts?.some((item) => normalizedFontName(item.expectedName) === normalizedFontName(fontName) && item.ready));
                  const missingFontIssues = issues.filter((item) => item.code === "FONT.NOT_EMBEDDED");
                  const allMissingFontsProvided = missingFontIssues.every((item) => report.providedFonts?.some(
                    (provided) => normalizedFontName(provided.expectedName) === normalizedFontName(fontNameFromIssue(item)) && provided.ready,
                  ));
                  const needsFontConfirmation = missingFontIssues.length > 0 && !allMissingFontsProvided;
                  const consented = Boolean(fontConsent[key]);
                  return (
                    <article className={`repair-task ${resolved ? "resolved" : ""}`} key={key}>
                      <div className="repair-task-head">
                        <span className={resolved ? "task-state done" : `severity ${issue.severity.toLowerCase()}`}>{resolved ? "DONE" : issue.severity}</span>
                        <div><h3>{issueNames[issue.code] ?? issue.code}</h3><p>{resolved ? resolvedDescriptions[issue.code] : issue.message}</p></div>
                      </div>
                      {!resolved && <div className="issue-action">
                        {issue.code === "PAGE.TRIMBOX_MISSING" && trimAction?.executable && <button disabled={busy} onClick={() => applySingleFix("trim_and_crop_marks", key)}>{isWorking ? "正在设置…" : "设置裁切框"}</button>}
                        {issue.code === "PAGE.BLEED_INSUFFICIENT" && bleedAction?.executable && <button disabled={busy} onClick={() => applySingleFix("bleed_and_crop", key)}>{isWorking ? "正在补出血…" : "安全补足出血"}</button>}
                        {issue.code === "PAGE.BLEED_INSUFFICIENT" && !bleedAction?.executable && <div className="manual-guidance"><b>需要回设计软件处理</b><span>将贴边背景或图片向裁切线外延展至少 3 mm；系统不会生成原设计中不存在的画面。</span></div>}
                        {issue.code === "IMAGE.LOW_EFFECTIVE_DPI" && <label className="asset-upload"><input type="file" accept="image/png,image/jpeg,image/tiff,image/webp,.png,.jpg,.jpeg,.tif,.tiff,.webp" disabled={busy} onChange={(event) => replaceImage(issue, event.target.files?.[0] ?? null)} /><span>{isWorking ? "正在替换并复检…" : "上传高分辨率原图"}</span><small>保持当前位置和尺寸，仅替换图片对象 · 当前 {String(evidence.dpi ?? "-")} PPI</small></label>}
                        {issue.code === "FONT.NOT_EMBEDDED" && <>
                          <label className="asset-upload"><input type="file" accept=".ttf,.otf,font/ttf,font/otf" disabled={busy} onChange={(event) => uploadFont(issue, event.target.files?.[0] ?? null)} /><span>{exactFontReady ? `原字体 ${fontName} 已就绪` : "上传原字体 TTF / OTF"}</span><small>系统会校验字体内部名称，名称不符不会使用。</small></label>
                          {!exactFontReady && <label className="inline-confirm"><input type="checkbox" checked={consented} onChange={(event) => setFontConsent((current) => ({ ...current, [key]: event.target.checked }))} /><span>没有原字体，允许候选导出使用替代字体；我会检查左侧字形与换行。</span></label>}
                          <button disabled={busy || (!exactFontReady && !consented) || !pdfxAction?.executable} onClick={() => applySingleFix("pdfx_candidate", key, !exactFontReady && consented)}>{isWorking ? "正在嵌入并复检…" : "嵌入字体并生成候选"}</button>
                        </>}
                        {(issue.code === "COLOR.RGB_USED" || issue.code === "PDFX.NOT_DECLARED") && <>
                          {needsFontConfirmation && <label className="inline-confirm"><input type="checkbox" checked={consented} onChange={(event) => setFontConsent((current) => ({ ...current, [key]: event.target.checked }))} /><span>当前仍缺字体，允许候选导出使用替代字体，并检查左侧预览。</span></label>}
                          <button disabled={busy || !pdfxAction?.executable || (needsFontConfirmation && !consented)} onClick={() => applySingleFix("pdfx_candidate", key, needsFontConfirmation && consented)}>{isWorking ? "正在转换并复检…" : "转换 CMYK / PDF/X-4"}</button>
                        </>}
                        <small className="rule-meta">规则 {issue.ruleVersion} · {Math.round(issue.confidence * 100)}% 置信度</small>
                      </div>}
                    </article>
                  );
                })}
              </div>
              {job.downloadAvailable && <button className="primary" disabled={busy} onClick={() => setDeliveryMode(true)}>完成修复，查看交付结果<span>→</span></button>}
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
      <footer><span>AI Print Production OS · Alpha MVP · <a href="https://github.com/allenxie0510/AIPrintProductionOS" target="_blank" rel="noreferrer">AGPL 源码</a></span><span>候选文件不能替代印厂打样与最终验收</span></footer>
    </main>
  );
}
