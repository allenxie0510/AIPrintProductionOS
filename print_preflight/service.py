from __future__ import annotations

import os
import math
import re
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
    inspect_font_file_isolated,
    replace_pdf_image_isolated,
    render_image_thumbnail_isolated,
    render_pdf_preview_isolated,
)
from .fixer import supports_pdfx4
from .geometry import TargetGeometry, target_geometry
from .job_store import JobStore
from .presets import PrintPreset, get_print_preset
from .profiles import resolve_cmyk_profile
from .rules import run_preflight


MAX_UPLOAD_BYTES = int(os.environ.get("PRINT_MVP_MAX_UPLOAD_BYTES", 100 * 1024 * 1024))
MAX_PAGES = int(os.environ.get("PRINT_MVP_MAX_PAGES", 20))
FILE_TTL_SECONDS = int(os.environ.get("PRINT_MVP_FILE_TTL_SECONDS", 24 * 60 * 60))
MAX_REPLACEMENT_IMAGE_BYTES = int(os.environ.get("PRINT_MVP_MAX_REPLACEMENT_IMAGE_BYTES", 50 * 1024 * 1024))
MAX_FONT_BYTES = int(os.environ.get("PRINT_MVP_MAX_FONT_BYTES", 20 * 1024 * 1024))


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
            if key not in {"absolutePath", "command", "stdout", "stderr", "source_path", "output_path", "profile"}
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
        geometry_issues = [issue for issue in issues if issue.get("code") == "PAGE.TARGET_SIZE_MISMATCH"]
        geometry_blocked = any(issue.get("fix", {}).get("safety") == "manual" for issue in geometry_issues)
        geometry_needs_normalization = any(
            issue.get("fix", {}).get("safety") == "confirm" for issue in geometry_issues
        )
        automatic_bleed = bool(bleed_issues) and all(
            issue.get("fix", {}).get("safety") == "auto"
            and issue.get("fix", {}).get("mode") == "solid_color_extend"
            for issue in bleed_issues
        )
        edge_bleed = bool(bleed_issues) and not automatic_bleed and all(
            issue.get("fix", {}).get("safety") == "confirm"
            and issue.get("fix", {}).get("mode") == "content_aware_or_manual"
            for issue in bleed_issues
        )
        bleed_executable = (automatic_bleed or edge_bleed) and not geometry_blocked
        trim_missing = "PAGE.TRIMBOX_MISSING" in codes
        target = preflight.get("policy", {}).get("targetGeometry") or {}
        target_label = target.get("label") or "目标"
        target_dimensions = (
            f"{target.get('widthMm'):g} × {target.get('heightMm'):g} mm"
            if isinstance(target.get("widthMm"), (int, float))
            and isinstance(target.get("heightMm"), (int, float))
            else "已确认尺寸"
        )
        unembedded = [font for font in analysis.get("document", {}).get("fonts", []) if not font.get("embedded")]
        try:
            resolve_cmyk_profile()
            pdfx_available = supports_pdfx4()
        except FileNotFoundError:
            pdfx_available = False

        return [
            {
                "action": "bleed_and_crop",
                "label": (
                    "扩展安全纯色背景并添加裁切标记"
                    if automatic_bleed
                    else "镜像延展边缘像素并添加裁切标记"
                ),
                "applicable": bool(bleed_issues),
                "executable": bleed_executable,
                "safety": "manual" if geometry_blocked else "auto" if automatic_bleed else "confirm" if edge_bleed else "manual",
                "method": "solid_color_extend" if automatic_bleed else "edge_pixel_mirror_extend" if edge_bleed else None,
                "reason": (
                    "PDF 页面比例与所选成品尺寸不一致；修正尺寸意图前不能安全生成出血。"
                    if geometry_blocked
                    else "所有页面边缘均被识别为高置信度均匀纯色，可确定性扩展出血。"
                    if automatic_bleed
                    else "以裁切线内侧边缘像素镜像生成 3 mm 出血；原 Trim Area 保持不变，执行后需查看预览。"
                    if edge_bleed
                    else "页面边缘无法安全生成出血，请返回设计软件延展贴边对象。"
                ),
            },
            {
                "action": "trim_and_crop_marks",
                "label": f"按 {target_label} {target_dimensions} 设置成品尺寸与裁切框",
                "applicable": trim_missing or bool(geometry_issues),
                "executable": (trim_missing or geometry_needs_normalization) and not geometry_blocked,
                "safety": "manual" if geometry_blocked else "confirm",
                "reason": (
                    "PDF 页面比例与所选成品尺寸不一致；请更正尺寸选择或返回设计软件调整画布。"
                    if geometry_blocked
                    else f"按设计师确认的 {target_label} {target_dimensions} 等比缩放整页并写入明确 TrimBox；不会生成出血。"
                ),
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

    @staticmethod
    def _action_summaries(actions: list[str]) -> list[str]:
        labels = {
            "bleed_and_crop": "已按 TrimBox 在裁切线外生成出血，并仅保留一套位于出血外侧的裁切标记。",
            "trim_and_crop_marks": "已设置明确裁切框并添加裁切标记；复杂出血仍需人工处理。",
            "pdfx_candidate": "已将整份 PDF 的全部页面批量转换为目标 CMYK，并生成 PDF/X-4 候选后重新检查。",
            "replace_image": "已在原版位置替换高分辨率图片并重新计算有效 PPI。",
        }
        return [labels[action] for action in actions if action in labels]

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

    @staticmethod
    def _base_pdf(job: dict[str, Any]) -> Path:
        existing_output = Path(job["output_path"]) if job.get("output_path") else None
        return existing_output if existing_output and existing_output.is_file() else Path(job["source_path"])

    @staticmethod
    def _target_geometry(job: dict[str, Any]) -> TargetGeometry | None:
        payload = job.get("target_geometry")
        return TargetGeometry.from_dict(payload) if payload else None

    @staticmethod
    def _normalized_font_name(value: str) -> str:
        without_subset = re.sub(r"^[A-Z]{6}\+", "", value or "")
        return re.sub(r"[^a-z0-9]", "", without_subset.lower())

    @staticmethod
    def _stream_asset(upload: BinaryIO, output: Path, *, maximum_bytes: int) -> int:
        written = 0
        with output.open("wb") as handle:
            while chunk := upload.read(1024 * 1024):
                written += len(chunk)
                if written > maximum_bytes:
                    handle.close()
                    output.unlink(missing_ok=True)
                    raise MvpError("ASSET_TOO_LARGE", f"Uploaded asset exceeds {maximum_bytes} bytes.", 413)
                handle.write(chunk)
        if written == 0:
            output.unlink(missing_ok=True)
            raise MvpError("ASSET_EMPTY", "Uploaded asset is empty.", 422)
        return written

    def _finalize_derivative(
        self,
        job: dict[str, Any],
        report: dict[str, Any],
        derivative: Path,
        fix_event: dict[str, Any],
    ) -> dict[str, Any]:
        job_id = job["id"]
        job_dir = self._job_dir(job_id)
        candidate = job_dir / "print-ready-candidate.pdf"
        self.store.update(job_id, status="validating")
        after_analysis = analyze_pdf_isolated(derivative, max_pages=MAX_PAGES)
        preset: PrintPreset = get_print_preset(job["preset_id"])
        before_preflight = report.get("afterPreflight") or report["preflight"]
        after_preflight = run_preflight(
            after_analysis,
            preset=preset,
            target=self._target_geometry(job),
        )
        if "pdfx_candidate" in fix_event.get("actions", []):
            before_low_ppi = [
                float((issue.get("evidence") or {}).get("dpi", preset.required_image_ppi))
                for issue in before_preflight.get("issues", [])
                if issue.get("code") == "IMAGE.LOW_EFFECTIVE_DPI"
            ]
            after_low_ppi = [
                float((issue.get("evidence") or {}).get("dpi", preset.required_image_ppi))
                for issue in after_preflight.get("issues", [])
                if issue.get("code") == "IMAGE.LOW_EFFECTIVE_DPI"
            ]
            baseline_floor = min(before_low_ppi, default=float(preset.required_image_ppi))
            if (
                len(after_low_ppi) > len(before_low_ppi)
                and min(after_low_ppi, default=baseline_floor) < baseline_floor * 0.9
            ):
                raise MvpError(
                    "FIX_QUALITY_REGRESSION",
                    "PDF/X conversion introduced additional lower-resolution raster objects. "
                    "The previous file was preserved; re-export from the design tool or ask the printer for a target preset.",
                    409,
                )
        resolved_by_action = {
            "bleed_and_crop": {
                "PAGE.TARGET_SIZE_MISMATCH",
                "PAGE.TRIMBOX_MISSING",
                "PAGE.BLEED_INSUFFICIENT",
            },
            "trim_and_crop_marks": {"PAGE.TRIMBOX_MISSING", "PAGE.TARGET_SIZE_MISMATCH"},
            "pdfx_candidate": {"COLOR.RGB_USED", "FONT.NOT_EMBEDDED", "PDFX.NOT_DECLARED"},
            "replace_image": {"IMAGE.LOW_EFFECTIVE_DPI"},
        }
        eligible_codes = {
            code
            for action in fix_event.get("actions", [])
            for code in resolved_by_action.get(action, set())
        }
        target_xref = (fix_event.get("target") or {}).get("xref")

        def still_present(before: dict[str, Any]) -> bool:
            for current in after_preflight.get("issues", []):
                if before.get("code") != current.get("code") or before.get("page") != current.get("page"):
                    continue
                if before.get("code") == "IMAGE.LOW_EFFECTIVE_DPI":
                    before_xref = (before.get("evidence") or {}).get("xref")
                    current_xref = (current.get("evidence") or {}).get("xref")
                    if before_xref == current_xref:
                        return True
                    continue
                if before.get("code") == "FONT.NOT_EMBEDDED":
                    if before.get("message") == current.get("message"):
                        return True
                    continue
                return True
            return False

        resolved_issues = []
        for issue in before_preflight.get("issues", []):
            if issue.get("code") not in eligible_codes:
                continue
            if issue.get("code") == "IMAGE.LOW_EFFECTIVE_DPI":
                if (issue.get("evidence") or {}).get("xref") != target_xref:
                    continue
            if not still_present(issue):
                resolved_issues.append(issue)
        fix_event = {**fix_event, "resolvedIssues": resolved_issues}
        validation = self._validate(derivative)
        status = "ready" if after_preflight["status"] != "FAIL" and validation["syntaxPassed"] else "partial"
        if derivative.resolve() != candidate.resolve():
            shutil.copy2(derivative, candidate)
        previous_history = (report.get("fix") or {}).get("history") or []
        fix_record = {**fix_event, "history": [*previous_history, fix_event]}
        previews = {
            **(report.get("previews") or {}),
            "current": self._preview_metadata(candidate, job_dir, stage="current"),
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
            output_path=str(candidate),
            fix_json=fix_record,
            report_json=updated_report,
            error_json=None,
        )
        return {**self.public_job(job_id), "report": updated_report}

    def create_job(
        self,
        upload: BinaryIO,
        filename: str | None,
        preset_id: str,
        size_id: str,
        trim_width_mm: float,
        trim_height_mm: float,
    ) -> dict[str, Any]:
        self.store.cleanup_expired()
        try:
            preset = get_print_preset(preset_id)
        except ValueError as error:
            raise MvpError("PRINT_PRESET_UNKNOWN", str(error), 422) from error
        try:
            target = target_geometry(size_id, trim_width_mm, trim_height_mm)
        except (TypeError, ValueError) as error:
            raise MvpError("TARGET_TRIM_SIZE_INVALID", str(error), 422) from error
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
            target_geometry=target.to_dict(),
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
            preflight = run_preflight(
                analysis,
                preset=get_print_preset(job["preset_id"]),
                target=self._target_geometry(job),
            )
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
            "targetGeometry": job.get("target_geometry"),
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
        provided_names = {
            self._normalized_font_name(item.get("expectedName", ""))
            for item in (report.get("providedFonts") or [])
            if item.get("ready")
        }
        unprovided = [
            font for font in unembedded
            if self._normalized_font_name(font.get("name", "")) not in provided_names
        ]
        if "pdfx_candidate" in actions and unprovided and not acknowledge_font_substitution:
            raise MvpError(
                "FONT_SUBSTITUTION_CONFIRMATION_REQUIRED",
                "PDF/X candidate export may substitute missing fonts. Explicit confirmation is required.",
                409,
            )

        job_dir = self._job_dir(job_id)
        working = self._base_pdf(job)
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
                    target=self._target_geometry(job),
                )
                fix_results.append(public_analysis(result, self.data_dir))
                working = boxed
            if "trim_and_crop_marks" in actions:
                trimmed = job_dir / f"trimmed-{stage_id}.pdf"
                result = add_trim_and_crop_marks_isolated(
                    working,
                    trimmed,
                    target=self._target_geometry(job),
                )
                fix_results.append(public_analysis(result, self.data_dir))
                working = trimmed
            if "pdfx_candidate" in actions:
                candidate = job_dir / f"pdfx-{stage_id}.pdf"
                profile = resolve_cmyk_profile()
                fonts_dir = job_dir / "fonts"
                result = export_pdfx4_cmyk_isolated(
                    working,
                    candidate,
                    profile,
                    job_dir,
                    font_dir=fonts_dir if fonts_dir.is_dir() else None,
                )
                fix_results.append(public_analysis(result, self.data_dir))
                working = candidate
            fix_event = {
                "actions": actions,
                "acknowledgedFontSubstitution": acknowledge_font_substitution,
                "results": fix_results,
                "summary": self._action_summaries(actions),
            }
            return self._finalize_derivative(job, report, working, fix_event)
        except MvpError as error:
            self.store.update(
                job_id,
                status=job["status"],
                error_json={"code": error.code, "message": error.message},
            )
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

    def replace_image(
        self,
        job_id: str,
        access_token: str,
        upload: BinaryIO,
        filename: str | None,
        *,
        xref: int,
    ) -> dict[str, Any]:
        job = self.require_job(job_id, access_token)
        if job["status"] not in {"awaiting_decision", "partial", "ready"}:
            raise MvpError("JOB_NOT_FIXABLE", "The job is not ready for an image replacement.", 409)
        report = job["report"]
        analysis = report.get("afterAnalysis") or report["analysis"]
        placements = [item for item in analysis["document"]["images"] if int(item["xref"]) == xref]
        if not placements:
            raise MvpError("IMAGE_TARGET_NOT_FOUND", "The selected image is no longer present in the current PDF.", 409)
        required_ppi = int((report.get("afterPreflight") or report["preflight"])["policy"]["requiredImagePpi"])
        required_width = max(
            math.ceil(item["pixelWidth"] * required_ppi / max(float(item["effectiveDpiX"]), 0.01))
            for item in placements
        )
        required_height = max(
            math.ceil(item["pixelHeight"] * required_ppi / max(float(item["effectiveDpiY"]), 0.01))
            for item in placements
        )

        job_dir = self._job_dir(job_id)
        assets_dir = job_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        safe_suffix = Path(filename or "replacement.png").suffix.lower()
        if safe_suffix not in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}:
            raise MvpError("IMAGE_FORMAT_UNSUPPORTED", "Use PNG, JPEG, TIFF or WebP for replacement.", 415)
        replacement = assets_dir / f"image-{xref}-{uuid4().hex[:10]}{safe_suffix}"
        self._stream_asset(upload, replacement, maximum_bytes=MAX_REPLACEMENT_IMAGE_BYTES)
        derivative = job_dir / f"image-replaced-{uuid4().hex[:10]}.pdf"
        self.store.update(job_id, status="fixing")
        try:
            result = replace_pdf_image_isolated(self._base_pdf(job), derivative, replacement, xref)
            if result["pixelWidth"] < required_width or result["pixelHeight"] < required_height:
                derivative.unlink(missing_ok=True)
                raise MvpError(
                    "REPLACEMENT_IMAGE_TOO_SMALL",
                    f"Replacement needs at least {required_width} × {required_height} pixels for this placement.",
                    422,
                )
            fix_event = {
                "actions": ["replace_image"],
                "summary": self._action_summaries(["replace_image"]),
                "target": {"xref": xref, "placements": len(placements)},
                "results": [public_analysis(result, self.data_dir)],
            }
            return self._finalize_derivative(job, report, derivative, fix_event)
        except MvpError:
            self.store.update(job_id, status=job["status"])
            raise
        except EngineProcessError as error:
            self.store.update(job_id, status=job["status"], error_json={"code": error.code, "message": error.message})
            raise MvpError(error.code, error.message, 422) from error
        except Exception as error:
            self.store.update(
                job_id,
                status=job["status"],
                error_json={"code": "IMAGE_REPLACEMENT_FAILED", "message": str(error)},
            )
            raise MvpError("IMAGE_REPLACEMENT_FAILED", str(error), 422) from error
        finally:
            replacement.unlink(missing_ok=True)

    def upload_font(
        self,
        job_id: str,
        access_token: str,
        upload: BinaryIO,
        filename: str | None,
        *,
        expected_name: str,
    ) -> dict[str, Any]:
        job = self.require_job(job_id, access_token)
        if job["status"] not in {"awaiting_decision", "partial", "ready"}:
            raise MvpError("JOB_NOT_FIXABLE", "The job is not ready for a font upload.", 409)
        report = job["report"]
        analysis = report.get("afterAnalysis") or report["analysis"]
        missing_names = [font["name"] for font in analysis["document"]["fonts"] if not font["embedded"]]
        requested = next(
            (name for name in missing_names if self._normalized_font_name(name) == self._normalized_font_name(expected_name)),
            None,
        )
        if requested is None:
            raise MvpError("FONT_TARGET_NOT_FOUND", "The selected missing font is no longer present.", 409)
        suffix = Path(filename or "font.ttf").suffix.lower()
        if suffix not in {".ttf", ".otf"}:
            raise MvpError("FONT_FORMAT_UNSUPPORTED", "Use a single-font TTF or OTF file.", 415)
        fonts_dir = self._job_dir(job_id) / "fonts"
        fonts_dir.mkdir(parents=True, exist_ok=True)
        font_path = fonts_dir / f"font-{uuid4().hex[:10]}{suffix}"
        self._stream_asset(upload, font_path, maximum_bytes=MAX_FONT_BYTES)
        try:
            inspected = inspect_font_file_isolated(font_path)
        except EngineProcessError as error:
            font_path.unlink(missing_ok=True)
            raise MvpError(error.code, error.message, 422) from error
        if self._normalized_font_name(inspected["name"]) != self._normalized_font_name(requested):
            font_path.unlink(missing_ok=True)
            raise MvpError(
                "FONT_NAME_MISMATCH",
                f"Uploaded font is {inspected['name']}, but the PDF requests {requested}. Upload the original font file.",
                422,
            )
        provided = [
            item for item in (report.get("providedFonts") or [])
            if self._normalized_font_name(item["expectedName"]) != self._normalized_font_name(requested)
        ]
        provided.append({"expectedName": requested, "fontName": inspected["name"], "ready": True})
        updated_report = {**report, "providedFonts": provided}
        self.store.update(job_id, report_json=updated_report, error_json=None)
        return {**self.public_job(job_id), "report": updated_report}

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

    def image_thumbnail_path(
        self,
        job_id: str,
        access_token: str,
        *,
        xref: int,
    ) -> Path:
        job = self.require_job(job_id, access_token)
        if xref <= 0:
            raise MvpError("IMAGE_TARGET_INVALID", "Image object reference must be positive.", 422)
        report = job.get("report") or {}
        analysis = report.get("afterAnalysis") or report.get("analysis") or {}
        images = analysis.get("document", {}).get("images", [])
        if not any(int(item.get("xref", 0)) == xref for item in images):
            raise MvpError("IMAGE_TARGET_NOT_FOUND", "The selected image is not present in the current PDF.", 404)
        source = self._base_pdf(job)
        digest = str(analysis.get("source", {}).get("sha256") or "current")[:12]
        output = self._job_dir(job_id) / f"image-thumbnail-{digest}-{xref}.png"
        if not output.is_file():
            try:
                render_image_thumbnail_isolated(source, output, xref=xref)
            except EngineProcessError as error:
                output.unlink(missing_ok=True)
                raise MvpError(error.code, error.message, 422) from error
        return output

    def delete(self, job_id: str, access_token: str) -> dict[str, Any]:
        self.require_job(job_id, access_token)
        deleted = self.store.delete_artifacts(job_id)
        return {"jobId": job_id, "deleted": deleted}
