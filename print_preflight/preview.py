from __future__ import annotations

import math
import io
import os
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageOps


MAX_PREVIEW_PIXELS = int(os.environ.get("PRINT_MVP_MAX_PREVIEW_PIXELS", "2500000"))
MAX_THUMBNAIL_SOURCE_PIXELS = int(os.environ.get("PRINT_MVP_MAX_THUMBNAIL_SOURCE_PIXELS", "50000000"))


def render_pdf_preview(
    input_pdf: str | Path,
    output_png: str | Path,
    *,
    page_number: int = 1,
    max_edge: int = 1400,
    max_pixels: int = MAX_PREVIEW_PIXELS,
) -> dict[str, Any]:
    if page_number < 1:
        raise ValueError("Preview page number must be positive.")
    if max_edge < 320 or max_edge > 2400:
        raise ValueError("Preview max edge must be between 320 and 2400 pixels.")

    source = Path(input_pdf).resolve()
    output = Path(output_png).resolve()
    with pymupdf.open(source) as document:
        if document.needs_pass:
            raise ValueError("Password-protected PDFs cannot be previewed.")
        if page_number > document.page_count:
            raise ValueError(f"Preview page {page_number} does not exist.")
        page = document.load_page(page_number - 1)
        rect = page.rect
        if rect.is_empty or rect.width <= 0 or rect.height <= 0:
            raise ValueError("PDF page has invalid preview geometry.")

        edge_scale = max_edge / max(rect.width, rect.height)
        pixel_scale = math.sqrt(max_pixels / (rect.width * rect.height))
        scale = max(0.1, min(edge_scale, pixel_scale, 2.5))
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        pixmap.save(output)

    return {
        "page": page_number,
        "width": pixmap.width,
        "height": pixmap.height,
        "format": "image/png",
        "maxEdge": max_edge,
    }


def render_image_thumbnail(
    input_pdf: str | Path,
    output_png: str | Path,
    *,
    xref: int,
    max_edge: int = 240,
) -> dict[str, Any]:
    """Extract a PDF image XObject into a bounded designer-facing thumbnail."""
    if xref <= 0:
        raise ValueError("Image object reference must be positive.")
    if max_edge < 96 or max_edge > 640:
        raise ValueError("Image thumbnail max edge must be between 96 and 640 pixels.")

    source = Path(input_pdf).resolve()
    output = Path(output_png).resolve()
    with pymupdf.open(source) as document:
        extracted = document.extract_image(xref)
    payload = extracted.get("image")
    if not payload:
        raise ValueError(f"Image object {xref} cannot be extracted from this PDF.")

    with Image.open(io.BytesIO(payload)) as embedded:
        if embedded.width * embedded.height > MAX_THUMBNAIL_SOURCE_PIXELS:
            raise ValueError("Image object exceeds the safe thumbnail pixel limit.")
        image = ImageOps.exif_transpose(embedded).convert("RGBA")
        image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
        background = Image.new("RGB", image.size, "white")
        background.paste(image, mask=image.getchannel("A"))
        output.parent.mkdir(parents=True, exist_ok=True)
        background.save(output, format="PNG", optimize=True)

    return {
        "xref": xref,
        "width": background.width,
        "height": background.height,
        "sourceWidth": int(extracted.get("width") or 0),
        "sourceHeight": int(extracted.get("height") or 0),
        "format": "image/png",
    }
