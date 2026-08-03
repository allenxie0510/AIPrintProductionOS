from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .presets import available_print_presets, get_print_preset
from .service import MvpError, PreflightService


DATA_DIR = Path(os.environ.get("PRINT_MVP_DATA_DIR", "var/mvp"))
service = PreflightService(DATA_DIR)

app = FastAPI(
    title="AI Print Production OS MVP API",
    version="0.1.0",
    description="Ephemeral PDF preflight, controlled repair and validation API.",
)
origins = [value.strip() for value in os.environ.get(
    "PRINT_MVP_CORS_ORIGINS",
    "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000",
).split(",") if value.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Job-Token"],
)


class FixRequest(BaseModel):
    actions: list[Literal["bleed_and_crop", "trim_and_crop_marks", "pdfx_candidate"]] = Field(min_length=1)
    acknowledgeFontSubstitution: bool = False


class FeedbackRequest(BaseModel):
    rating: Literal["accepted", "partially_correct", "incorrect", "undone"]
    ruleId: str | None = None
    reason: str | None = Field(default=None, max_length=1000)
    printerOutcome: Literal[
        "printer_accepted",
        "printer_rejected",
        "printed_successfully",
        "printed_with_issues",
        "unknown",
    ] | None = None


@app.exception_handler(MvpError)
async def mvp_error_handler(_request: Request, error: MvpError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"error": {"code": error.code, "message": error.message}},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ai-print-production-os-mvp"}


@app.get("/v1/presets")
def presets() -> dict[str, list[dict]]:
    return {"presets": [get_print_preset(preset_id).to_dict() for preset_id in available_print_presets()]}


@app.post("/v1/jobs", status_code=202)
def create_job(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="PDF document")],
    presetId: Annotated[str, Form()] = "designer-standard-poc",
) -> dict:
    try:
        result = service.create_job(file.file, file.filename, presetId)
        background_tasks.add_task(service.analyze_job, result["jobId"])
        return result
    finally:
        file.file.close()


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, access_token: Annotated[str, Header(alias="X-Job-Token")]) -> dict:
    service.require_job(job_id, access_token)
    return service.public_job(job_id)


@app.get("/v1/jobs/{job_id}/report")
def get_report(job_id: str, access_token: Annotated[str, Header(alias="X-Job-Token")]) -> dict:
    return service.report(job_id, access_token)


@app.get("/v1/jobs/{job_id}/preview")
def preview(
    job_id: str,
    access_token: Annotated[str, Header(alias="X-Job-Token")],
    stage: Literal["source", "current"] = "source",
    page: int = 1,
) -> FileResponse:
    output = service.preview_path(
        job_id,
        access_token,
        stage=stage,
        page_number=page,
    )
    return FileResponse(
        output,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


@app.post("/v1/jobs/{job_id}/fix")
def fix_job(
    job_id: str,
    payload: FixRequest,
    access_token: Annotated[str, Header(alias="X-Job-Token")],
) -> dict:
    return service.apply_fixes(
        job_id,
        access_token,
        list(payload.actions),
        payload.acknowledgeFontSubstitution,
    )


@app.post("/v1/jobs/{job_id}/assets/image-replacement")
def replace_image(
    job_id: str,
    file: Annotated[UploadFile, File(description="High-resolution replacement image")],
    xref: Annotated[int, Form()],
    access_token: Annotated[str, Header(alias="X-Job-Token")],
) -> dict:
    try:
        return service.replace_image(
            job_id,
            access_token,
            file.file,
            file.filename,
            xref=xref,
        )
    finally:
        file.file.close()


@app.post("/v1/jobs/{job_id}/assets/font")
def upload_font(
    job_id: str,
    file: Annotated[UploadFile, File(description="Original TTF or OTF font")],
    expectedName: Annotated[str, Form()],
    access_token: Annotated[str, Header(alias="X-Job-Token")],
) -> dict:
    try:
        return service.upload_font(
            job_id,
            access_token,
            file.file,
            file.filename,
            expected_name=expectedName,
        )
    finally:
        file.file.close()


@app.get("/v1/jobs/{job_id}/download")
def download(job_id: str, access_token: Annotated[str, Header(alias="X-Job-Token")]) -> FileResponse:
    output, name = service.download_path(job_id, access_token)
    return FileResponse(output, media_type="application/pdf", filename=name)


@app.delete("/v1/jobs/{job_id}/artifacts")
def delete_artifacts(job_id: str, access_token: Annotated[str, Header(alias="X-Job-Token")]) -> dict:
    return service.delete(job_id, access_token)


@app.post("/v1/jobs/{job_id}/feedback", status_code=201)
def feedback(
    job_id: str,
    payload: FeedbackRequest,
    access_token: Annotated[str, Header(alias="X-Job-Token")],
) -> dict[str, bool]:
    service.require_job(job_id, access_token)
    service.store.add_feedback(
        job_id,
        rating=payload.rating,
        rule_id=payload.ruleId,
        reason=payload.reason,
        printer_outcome=payload.printerOutcome,
    )
    return {"recorded": True}
