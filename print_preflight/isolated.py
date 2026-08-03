from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ENGINE_TIMEOUT_SECONDS = int(os.environ.get("PRINT_MVP_ENGINE_TIMEOUT_SECONDS", "120"))


class EngineProcessError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run(stage_args: list[str], work_dir: Path) -> Any:
    work_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=work_dir, prefix=".engine-result-", suffix=".json", delete=False) as handle:
        result_path = Path(handle.name)
    result_path.unlink(missing_ok=True)
    command = [sys.executable, "-m", "print_preflight.engine_worker", "--result", str(result_path), *stage_args]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=ENGINE_TIMEOUT_SECONDS,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as error:
        raise EngineProcessError(
            "ENGINE_TIMEOUT",
            f"PDF processing exceeded the {ENGINE_TIMEOUT_SECONDS}-second safety limit.",
        ) from error
    try:
        envelope = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else None
    except (json.JSONDecodeError, OSError):
        envelope = None
    finally:
        result_path.unlink(missing_ok=True)

    if isinstance(envelope, dict) and not envelope.get("ok"):
        error = envelope.get("error") or {}
        raise EngineProcessError(
            str(error.get("code") or "ENGINE_STAGE_FAILED"),
            str(error.get("message") or "PDF processing failed."),
        )
    if completed.returncode != 0 or not isinstance(envelope, dict):
        resource_exit = completed.returncode in {-signal.SIGKILL, -signal.SIGXCPU, 137}
        raise EngineProcessError(
            "ENGINE_RESOURCE_LIMIT" if resource_exit else "ENGINE_PROCESS_FAILED",
            "PDF processing exceeded a safe resource limit. Try a simpler export or contact support."
            if resource_exit
            else "The isolated PDF engine stopped unexpectedly.",
        )
    return envelope.get("result")


def analyze_pdf_isolated(source: Path, *, max_pages: int) -> dict[str, Any]:
    return _run(["analyze", str(source), "--max-pages", str(max_pages)], source.parent)


def add_bleed_and_crop_marks_isolated(
    source: Path,
    output: Path,
    analysis: dict[str, Any],
    *,
    bleed_mm: float,
) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output.parent,
        prefix=".analysis-",
        suffix=".json",
        delete=False,
    ) as handle:
        json.dump(analysis, handle, ensure_ascii=False)
        analysis_path = Path(handle.name)
    try:
        return _run(
            ["bleed", str(source), str(output), str(analysis_path), "--bleed-mm", str(bleed_mm)],
            output.parent,
        )
    finally:
        analysis_path.unlink(missing_ok=True)


def export_pdfx4_cmyk_isolated(
    source: Path,
    output: Path,
    profile: Path,
    work_dir: Path,
) -> dict[str, Any]:
    return _run(["pdfx", str(source), str(output), str(profile), str(work_dir)], work_dir)
