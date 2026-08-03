from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any

import pymupdf


MAX_PREVIEW_PIXELS = int(os.environ.get("PRINT_MVP_MAX_PREVIEW_PIXELS", "2500000"))


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
