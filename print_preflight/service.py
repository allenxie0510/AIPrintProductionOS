from __future__ import annotations

import os
import secrets
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, BinaryIO
from uuid import uuid4

from .isolated import (
    EngineProcessError,
    add_bleed_and_crop_marks_isolated,
    add_trim_and_crop_marks_isolated,
    analyze_pdf_isolated,
    export_pdfx4_cmyk_isolated,
    render_pdf_preview_isolated,
)
from .fixer import supports_pdfx4
from .job_store import JobStore
from .presets import PrintPreset, get_print_preset
from .profiles import resolve_cmyk_profile
from .rules import run_preflight


MAX_UPLOAD_BYTES = int(os.environ.get("PRINT_MVP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024))
MAX_PAGES = int(os.environ.get("PRINT_MVP_MAX_PAGES", 20))
FILE_TTL_SECONDS = int(os.environ.get("PRINT_MVP_FILE_TTL_SECONDS", 24 * 60 * 60))


class MvpError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def public_analysis(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {
            key: public_analysis(item, root)
            for key, item in value.items()
            if key not in {"absolutePath", "command", "stdout", "stderr", "source_path", "output_path"}
        }
    if isinstance(value, list):
        return [public_analysis(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(root) + "/", "")
    return value


class PreflightService:
    def __init__(self, data_dir: str | Path) -> None:
        self.store = JobStore(data_dir)
        self.data_dir = self.store.data_dir

    def _job_dir(self, job_id: str) -> Path:
        target = (self.store.jobs_dir / job_id).resolve()
        if target.parent != self.store.jobs_dir:
            raise MvpError("JOB_PATH_INVALID", "Invalid job path.", 500)
        return target

    @staticmethod
    def _safe_name(name: str | None) -> str:
        candidate = Path(name or "upload.pdf").name
        return candidate[:180] or "upload.pdf"

    @staticmethod
    def _fix_plan(analysis: dict[str, Any], preflight: dict[str, Any]) -> list[dict[str, Any]]:
        issues = preflight.get("issues") or []
        codes = {issue.get("code") for issue in issues}
        bleed_issues = [issue for issue in issues if issue.get("code") == "PAGE.BLEED_INSUFFICIENT"]
        automatic_bleed = bool(bleed_issues) and all(
            issue.get("fix", {}).get("safety") == "auto"
            and issue.get("fix", {}).get("mode") == "solid_color_extend"
            for issue in bleed_issues
        )
        trim_missing = "PAGE.TRIMBOX_MISSING" in codes
        unembedded = [font for font in analysis.get("document", {}).get("fonts", []) if not font.get("embedded")]
        try:
            resolve_cmyk_profile()
            pdfx_available = supports_pdfx4()
        except FileNotFoundError:
            pdfx_available = False

        return [
            {
                "action": "bleed_and_crop",
                "label": "扩展安全纯色背景并添加裁切标记",
                "applicable": bool(bleed_issues),
                "executable": automatic_bleed,
                "safety": "auto" if automatic_bleed else "manual",
                "reason": (
                    "所有页面边缘均被识别为高置信度均匀纯色，可确定性扩展出血。"
                    if automatic_bleed
                    else "页面边缘包含复杂内容，不能在不生成新画面的前提下安全补足出血。"
                ),
            },
            {
                "action": "trim_and_crop_marks",
                "label": "设置裁切框并添加裁切标记",
                "applicable": trim_missing and not automatic_bleed,
                "executable": trim_missing and not automatic_bleed,
                "safety": "confirm",
                "reason": "扩展页面工作区并明确 TrimBox；不会生成或声明不存在的出血。",
            },
            {
                "action": "pdfx_candidate",
                "label": "生成 CMYK / PDF/X-4 候选文件",
                "applicable": bool({"COLOR.RGB_USED", "PDFX.NOT_DECLARED", "FONT.NOT_EMBEDDED"} & codes),
                "executable": pdfx_available,
                "safety": "confirm",
                "reason": (
                    "使用配置的目标 ICC 与 Ghostscript 生成候选文件；仍需印厂按目标印刷条件验证。"
                    if pdfx_available
                    else "当前处理器缺少兼容的 Ghostscript（>= 10.07）或 CMYK ICC 配置。"
                ),
                "requiresFontAcknowledgement": bool(unembedded),
            },
        ]

    def _preview_metadata(
        self,
        pdf_path: Path,
        job_dir: Path,
        *,
        stage: str,
        page_number: int = 1,
    ) -> dict[str, Any]:
        output = job_dir / f"{stage}-preview-page-{page_number}.png"
        try:
            rendered = render_pdf_preview_isolated(
                pdf_path,
                output,
                page_number=page_number,
            )
            return {
                "available": True,
                "stage": stage,
                "page": page_number,
                "width": rendered.get("width"),
                "height": rendered.get("height"),
            }
        except EngineProcessError as error:
            output.unlink(missing_ok=True)
            return {
                "available": False,
                "stage": stage,
                "page": page_number,
                "reason": error.code,
            }

    def create_job(self, upload: BinaryIO, filename: str | None, preset_id: str) -> dict[str, Any]:
        self.store.cleanup_expired()
        try:
            preset = get_print_preset(preset_id)
        except ValueError as error:
            raise MvpError("PRINT_PRESET_UNKNOWN", str(error), 422) from error
        job_id = uuid4().hex
        access_token = secrets.token_urlsafe(32)
        job_dir = self._job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=False)
        source = job_dir / "source.pdf"
        written = 0
        with source.open("wb") as handle:
            while chunk := upload.read(1024 * 1024):
                written += len(chunk)
                if written > MAX_UPLOAD_BYTES:
                    handle.close()
                    shutil.rmtree(job_dir)
                    raise MvpError("FILE_TOO_LARGE", f"PDF exceeds {MAX_UPLOAD_BYTES} bytes.", 413)
                handle.write(chunk)
        with source.open("rb") as handle:
            signature = handle.read(5)
        if written < 5 or signature != b"%PDF-":
            shutil.rmtree(job_dir)
            raise MvpError("INVALID_PDF_SIGNATURE", "The uploaded file is not a PDF.", 415)

        expires = (datetime.now(UTC) + timedelta(seconds=FILE_TTL_SECONDS)).isoformat()
        self.store.create_job(
            job_id=job_id,
            access_token=access_token,
            original_name=self._safe_name(filename),
            preset_id=preset.preset_id,
            source_path=source,
            expires_at=expires,
        )
        return {"jobId": job_id, "accessToken": access_token, **self.public_job(job_id)}

    def analyze_job(self, job_id: str) -> None:
        job = self.store.get_job(job_id)
        if job is None or not job.get("source_path"):
            return
        source = Path(job["source_path"])
        self.store.update(job_id, status="analyzing")
        try:
            analysis = analyze_pdf_isolated(source, max_pages=MAX_PAGES)
            preflight = run_preflight(analysis, preset=get_print_preset(job["preset_id"]))
            preview = self._preview_metadata(source, self._job_dir(job_id), stage="source")
            report = {
                "analysis": public_analysis(analysis, self.data_dir),
                "preflight": preflight,
                "fixPlan": self._fix_plan(analysis, preflight),
                "previews": {"source": preview},
                "validation": None,
                "fix": None,
            }
            self.store.update(job_id, status="awaiting_decision", report_json=report)
        except MvpError as error:
            self.store.update(job_id, status="failed", error_json={"code": error.code, "message": error.message})
            return
        except EngineProcessError as error:
            self.store.update(job_id, status="failed", error_json={"code": error.code, "message": error.message})
            return
        except Exception as error:
            self.store.update(
                job_id,
                status="failed",
                error_json={"code": "ANALYSIS_FAILED", "message": str(error)},
            )
            return

    def require_job(self, job_id: str, access_token: str) -> dict[str, Any]:
        job = self.store.authorize(job_id, access_token)
        if job is None:
            raise MvpError("JOB_NOT_FOUND", "Job not found or access token is invalid.", 404)
        return job

    def public_job(self, job_id: str) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        if job is None:
            raise MvpError("JOB_NOT_FOUND", "Job not found.", 404)
        report = job.get("report") or {}
        preflight = report.get("afterPreflight") or report.get("preflight") or {}
        return {
            "jobId": job["id"],
            "fileName": job["original_name"],
            "presetId": job["preset_id"],
            "status": job["status"],
            "createdAt": job["created_at"],
            "updatedAt": job["updated_at"],
            "expiresAt": job["expires_at"],
            "filesDeletedAt": job["files_deleted_at"],
            "summary": preflight.get("summary"),
            "productionScore": preflight.get("productionScore"),
            "error": job.get("error"),
            "downloadAvailable": bool(job.get("output_path") and Path(job["output_path"]).is_file()),
        }

    def report(self, job_id: str, access_token: str) -> dict[str, Any]:
        job = self.require_job(job_id, access_token)
        if not job.get("report"):
            raise MvpError("REPORT_NOT_READY", "The report is not ready.", 409)
        return job["report"]

    def apply_fixes(
        self,
        job_id: str,
        access_token: str,
        actions: list[str],
        acknowledge_font_substitution: bool,
    ) -> dict[str, Any]:
        job = self.require_job(job_id, access_token)
        if job["status"] not in {"awaiting_decision", "partial", "ready"}:
            raise MvpError("JOB_NOT_FIXABLE", "The job is not ready for a fix plan.", 409)
        allowed = {"bleed_and_crop", "trim_and_crop_marks", "pdfx_candidate"}
        if not actions or set(actions) - allowed:
            raise MvpError("FIX_PLAN_INVALID", "Select at least one supported fix action.", 422)
        report = job["report"]
        analysis = report.get("afterAnalysis") or report["analysis"]
        preflight = report.get("afterPreflight") or report["preflight"]
        plan = {item["action"]: item for item in self._fix_plan(analysis, preflight)}
        unsafe = [action for action in actions if not plan.get(action, {}).get("executable")]
        if unsafe:
            reason = plan.get(unsafe[0], {}).get("reason") or "The selected action cannot be executed safely."
            raise MvpError("FIX_ACTION_UNSAFE", reason, 409)
        if {"bleed_and_crop", "trim_and_crop_marks"}.issubset(actions):
            raise MvpError("FIX_PLAN_INVALID", "Bleed extension and trim-only repair are mutually exclusive.", 422)
        unembedded = [font for font in analysis["document"]["fonts"] if not font["embedded"]]
        if "pdfx_candidate" in actions and unembedded and not acknowledge_font_substitution:
            raise MvpError(
                "FONT_SUBSTITUTION_CONFIRMATION_REQUIRED",
                "PDF/X candidate export may substitute missing fonts. Explicit confirmation is required.",
                409,
            )

        source = Path(job["source_path"])
        job_dir = self._job_dir(job_id)
        existing_output = Path(job["output_path"]) if job.get("output_path") else None
        working = existing_output if existing_output and existing_output.is_file() else source
        stage_id = uuid4().hex[:10]
        fix_results: list[dict[str, Any]] = []
        self.store.update(job_id, status="fixing")
        try:
            if "bleed_and_crop" in actions:
                boxed = job_dir / f"boxed-{stage_id}.pdf"
                result = add_bleed_and_crop_marks_isolated(
                    working,
                    boxed,
                    analyze_pdf_isolated(working, max_pages=MAX_PAGES),
                    bleed_mm=get_print_preset(job["preset_id"]).bleed_mm,
                )
                fix_results.append(public_analysis(result, self.data_dir))
                working = boxed
            if "trim_and_crop_marks" in actions:
                trimmed = job_dir / f"trimmed-{stage_id}.pdf"
                result = add_trim_and_crop_marks_isolated(working, trimmed)
                fix_results.append(public_analysis(result, self.data_dir))
                working = trimmed
            if "pdfx_candidate" in actions:
                candidate = job_dir / f"pdfx-{stage_id}.pdf"
                profile = resolve_cmyk_profile()
                result = export_pdfx4_cmyk_isolated(working, candidate, profile, job_dir)
                fix_results.append(public_analysis(result, self.data_dir))
                working = candidate
            candidate = job_dir / "print-ready-candidate.pdf"
            if working.resolve() != candidate.resolve():
                shutil.copy2(working, candidate)
            working = candidate

            self.store.update(job_id, status="validating")
            after_analysis = analyze_pdf_isolated(working, max_pages=MAX_PAGES)
            preset: PrintPreset = get_print_preset(job["preset_id"])
            after_preflight = run_preflight(after_analysis, preset=preset)
            validation = self._validate(working)
            status = "ready" if after_preflight["status"] != "FAIL" and validation["syntaxPassed"] else "partial"
            fix_event = {
                "actions": actions,
                "acknowledgedFontSubstitution": acknowledge_font_substitution,
                "results": fix_results,
            }
            previous_history = (report.get("fix") or {}).get("history") or []
            fix_record = {**fix_event, "history": [*previous_history, fix_event]}
            previews = {
                **(report.get("previews") or {}),
                "current": self._preview_metadata(working, job_dir, stage="current"),
            }
            updated_report = {
                **report,
                "fix": fix_record,
                "afterAnalysis": public_analysis(after_analysis, self.data_dir),
                "afterPreflight": after_preflight,
                "fixPlan": self._fix_plan(after_analysis, after_preflight),
                "previews": previews,
                "validation": validation,
            }
            self.store.update(
                job_id,
                status=status,
                output_path=str(working),
                fix_json=fix_record,
                report_json=updated_report,
            )
            return {**self.public_job(job_id), "report": updated_report}
        except MvpError:
            raise
        except EngineProcessError as error:
            self.store.update(
                job_id,
                status="awaiting_decision",
                error_json={"code": error.code, "message": error.message},
            )
            raise MvpError(error.code, error.message, 422) from error
        except Exception as error:
            self.store.update(
                job_id,
                status="awaiting_decision",
                error_json={"code": "FIX_FAILED", "message": str(error)},
            )
            raise MvpError("FIX_FAILED", str(error), 422) from error

    @staticmethod
    def _validate(pdf_path: Path) -> dict[str, Any]:
        qpdf = shutil.which("qpdf")
        if not qpdf:
            return {
                "syntaxPassed": False,
                "validator": "qpdf-unavailable",
                "pdfxState": "candidate_not_independently_validated",
            }
        completed = subprocess.run(
            [qpdf, "--check", str(pdf_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        message = (completed.stdout + completed.stderr).strip().replace(str(pdf_path), pdf_path.name)
        return {
            "syntaxPassed": completed.returncode == 0,
            "validator": "qpdf-syntax-only",
            "pdfxState": "candidate_not_independently_validated",
            "message": message,
        }

    def download_path(self, job_id: str, access_token: str) -> tuple[Path, str]:
        job = self.require_job(job_id, access_token)
        output = Path(job["output_path"]) if job.get("output_path") else None
        if output is None or not output.is_file():
            raise MvpError("OUTPUT_NOT_READY", "No output file is available.", 409)
        return output, f"{Path(job['original_name']).stem}-print-ready-candidate.pdf"

    def preview_path(
        self,
        job_id: str,
        access_token: str,
        *,
        stage: str,
        page_number: int,
    ) -> Path:
        job = self.require_job(job_id, access_token)
        if page_number < 1 or page_number > MAX_PAGES:
            raise MvpError("PREVIEW_PAGE_INVALID", f"Preview page must be between 1 and {MAX_PAGES}.", 422)
        if stage not in {"source", "current"}:
            raise MvpError("PREVIEW_STAGE_INVALID", "Preview stage must be source or current.", 422)
        pdf_value = job.get("source_path") if stage == "source" else job.get("output_path")
        if not pdf_value or not Path(pdf_value).is_file():
            raise MvpError("PREVIEW_NOT_READY", "The requested preview is not ready.", 409)
        job_dir = self._job_dir(job_id)
        preview = job_dir / f"{stage}-preview-page-{page_number}.png"
        if not preview.is_file():
            metadata = self._preview_metadata(Path(pdf_value), job_dir, stage=stage, page_number=page_number)
            if not metadata.get("available"):
                raise MvpError("PREVIEW_FAILED", "The PDF preview could not be rendered safely.", 422)
        return preview

    def delete(self, job_id: str, access_token: str) -> dict[str, Any]:
        self.require_job(job_id, access_token)
        deleted = self.store.delete_artifacts(job_id)
        return {"jobId": job_id, "deleted": deleted}
