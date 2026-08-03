from __future__ import annotations

import io
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, RectangleObject
from reportlab.pdfgen import canvas

from .units import PT_PER_MM


MIN_GHOSTSCRIPT_PDFX4 = (10, 7)
MAX_REPLACEMENT_IMAGE_PIXELS = 50_000_000


def inspect_font_file(font_file: str | Path) -> dict[str, Any]:
    source = Path(font_file).resolve()
    signature = source.read_bytes()[:4]
    if signature not in {b"OTTO", b"\x00\x01\x00\x00", b"true"}:
        raise ValueError("Only valid single-font TTF or OTF files are supported.")
    font = pymupdf.Font(fontfile=str(source))
    return {
        "name": font.name,
        "glyphCount": font.glyph_count,
        "isBold": bool(font.is_bold),
        "isItalic": bool(font.is_italic),
    }


def replace_pdf_image(
    input_pdf: str | Path,
    output_pdf: str | Path,
    image_file: str | Path,
    xref: int,
) -> dict[str, Any]:
    replacement = Path(image_file).resolve()
    with Image.open(replacement) as image:
        image.verify()
    with Image.open(replacement) as image:
        width, height = image.size
        image_format = image.format
    if width <= 0 or height <= 0 or width * height > MAX_REPLACEMENT_IMAGE_PIXELS:
        raise ValueError("Replacement image exceeds the safe 50 megapixel limit.")

    source = Path(input_pdf).resolve()
    output = Path(output_pdf).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open(source) as document:
        page_numbers = [
            page.number + 1
            for page in document
            if any(int(item[0]) == xref for item in page.get_images(full=True))
        ]
        if not page_numbers:
            raise ValueError(f"Image object {xref} is not present in the current PDF.")
        document[page_numbers[0] - 1].replace_image(xref, filename=str(replacement))
        document.save(output, garbage=4, deflate=True)
    return {
        "strategy": "replace_image_source",
        "xref": xref,
        "pages": page_numbers,
        "pixelWidth": width,
        "pixelHeight": height,
        "format": image_format,
        "output": str(output),
    }


def ghostscript_version(executable: str | None = None) -> tuple[int, ...] | None:
    gs = executable or shutil.which("gs")
    if not gs:
        return None
    completed = subprocess.run([gs, "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", completed.stdout or completed.stderr)
    if completed.returncode != 0 or not match:
        return None
    return tuple(int(part) for part in match.groups(default="0"))


def supports_pdfx4(executable: str | None = None) -> bool:
    version = ghostscript_version(executable)
    return bool(version and version[:2] >= MIN_GHOSTSCRIPT_PDFX4)


def _marks_overlay(width: float, height: float, trim: tuple[float, float, float, float],
                   bleed_pt: float, rgb: tuple[int, int, int] | None) -> bytes:
    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1)
    tx0, ty0, tx1, ty1 = trim
    if rgb is not None:
        c.setFillColorRGB(*(value / 255.0 for value in rgb))
        c.rect(tx0 - bleed_pt, ty0 - bleed_pt, (tx1 - tx0) + 2 * bleed_pt,
               (ty1 - ty0) + 2 * bleed_pt, stroke=0, fill=1)

    gap = 1.0
    line_length = 5.0 * PT_PER_MM
    bleed_left = tx0 - bleed_pt
    bleed_right = tx1 + bleed_pt
    bleed_bottom = ty0 - bleed_pt
    bleed_top = ty1 + bleed_pt
    c.setStrokeColorCMYK(0, 0, 0, 1)
    c.setLineWidth(0.25)
    for x in (tx0, tx1):
        c.line(x, bleed_bottom - gap - line_length, x, bleed_bottom - gap)
        c.line(x, bleed_top + gap, x, bleed_top + gap + line_length)
    for y in (ty0, ty1):
        c.line(bleed_left - gap - line_length, y, bleed_left - gap, y)
        c.line(bleed_right + gap, y, bleed_right + gap + line_length, y)
    c.showPage()
    c.save()
    return stream.getvalue()


def _marks_overlay_page(
    width: float,
    height: float,
    trim: tuple[float, float, float, float],
    bleed_pt: float,
    rgb: tuple[int, int, int] | None,
):
    page = PdfReader(io.BytesIO(_marks_overlay(width, height, trim, bleed_pt, rgb))).pages[0]
    resources = page.get("/Resources")
    if resources and NameObject("/Font") in resources:
        del resources[NameObject("/Font")]
    return page


def add_trim_and_crop_marks(
    input_pdf: str | Path,
    output_pdf: str | Path,
    *,
    slug_mm: float = 8.0,
) -> dict[str, Any]:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    slug_pt = slug_mm * PT_PER_MM
    page_results = []

    for index, source_page in enumerate(reader.pages):
        source_width = float(source_page.mediabox.width)
        source_height = float(source_page.mediabox.height)
        output_width = source_width + 2 * slug_pt
        output_height = source_height + 2 * slug_pt
        trim = (slug_pt, slug_pt, slug_pt + source_width, slug_pt + source_height)
        overlay_page = _marks_overlay_page(output_width, output_height, trim, 0.0, None)
        target = writer.add_blank_page(width=output_width, height=output_height)
        target.merge_page(overlay_page)
        tx = slug_pt - float(source_page.mediabox.left)
        ty = slug_pt - float(source_page.mediabox.bottom)
        target.merge_transformed_page(source_page, Transformation().translate(tx=tx, ty=ty), over=True)
        target.mediabox = RectangleObject([0, 0, output_width, output_height])
        target.cropbox = RectangleObject([0, 0, output_width, output_height])
        target.trimbox = RectangleObject(list(trim))
        page_results.append({
            "page": index + 1,
            "strategy": "trim_and_crop_marks",
            "slugMm": slug_mm,
            "cropMarksAdded": True,
            "bleedGenerated": False,
        })

    output = Path(output_pdf)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    return {"output": str(output.resolve()), "pages": page_results}


def add_bleed_and_crop_marks(input_pdf: str | Path, output_pdf: str | Path, analysis: dict[str, Any],
                             bleed_mm: float = 3.0, slug_mm: float = 8.0) -> dict[str, Any]:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    bleed_pt = bleed_mm * PT_PER_MM
    slug_pt = slug_mm * PT_PER_MM
    page_results = []

    for index, source_page in enumerate(reader.pages):
        classification = analysis["pages"][index]["border"]
        if classification["automationSafety"] != "auto":
            raise ValueError(f"Page {index + 1} border is not safe for automatic solid-color bleed")
        rgb = tuple(classification["sampledRgb"])
        source_width = float(source_page.mediabox.width)
        source_height = float(source_page.mediabox.height)
        margin = bleed_pt + slug_pt
        output_width = source_width + 2 * margin
        output_height = source_height + 2 * margin
        trim = (margin, margin, margin + source_width, margin + source_height)

        overlay_page = _marks_overlay_page(output_width, output_height, trim, bleed_pt, rgb)
        target = writer.add_blank_page(width=output_width, height=output_height)
        target.merge_page(overlay_page)
        tx = margin - float(source_page.mediabox.left)
        ty = margin - float(source_page.mediabox.bottom)
        target.merge_transformed_page(source_page, Transformation().translate(tx=tx, ty=ty), over=True)
        target.mediabox = RectangleObject([0, 0, output_width, output_height])
        target.cropbox = RectangleObject([0, 0, output_width, output_height])
        target.trimbox = RectangleObject(list(trim))
        target.bleedbox = RectangleObject([
            trim[0] - bleed_pt,
            trim[1] - bleed_pt,
            trim[2] + bleed_pt,
            trim[3] + bleed_pt,
        ])
        page_results.append({
            "page": index + 1,
            "strategy": "solid_color_extend",
            "sampledRgb": list(rgb),
            "bleedMm": bleed_mm,
            "slugMm": slug_mm,
            "cropMarksAdded": True,
        })

    output = Path(output_pdf)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    return {"output": str(output.resolve()), "pages": page_results}


def _pdfx_definition(profile: Path, title: str) -> str:
    profile_ps = str(profile.resolve()).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    safe_title = title.replace("(", "[").replace(")", "]")
    return f"""%!
/ICCProfile ({profile_ps}) def
[/GTS_PDFXVersion (PDF/X-4) /Title ({safe_title}) /Trapped /False /DOCINFO pdfmark
[/_objdef {{icc_PDFX}} /type /stream /OBJ pdfmark
[{{icc_PDFX}} << /N 4 >> /PUT pdfmark
[{{icc_PDFX}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFX}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFX}} <<
  /Type /OutputIntent
  /S /GTS_PDFX
  /OutputCondition (POC Generic CMYK - NOT FOR PRODUCTION)
  /Info (macOS Generic CMYK Profile used only for technical validation)
  /OutputConditionIdentifier (POC_GENERIC_CMYK)
  /RegistryName (https://www.color.org)
  /DestOutputProfile {{icc_PDFX}}
>> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFX}} ] >> /PUT pdfmark
"""


def export_pdfx4_cmyk(input_pdf: str | Path, output_pdf: str | Path, cmyk_profile: str | Path,
                      work_dir: str | Path, *, font_dir: str | Path | None = None) -> dict[str, Any]:
    gs = shutil.which("gs")
    if not gs:
        raise RuntimeError("Ghostscript is required for this POC step")
    version = ghostscript_version(gs)
    if not supports_pdfx4(gs):
        rendered = ".".join(str(part) for part in version) if version else "unknown"
        raise RuntimeError(f"PDF/X-4 POC export requires Ghostscript >= 10.07; found {rendered}")
    profile = Path(cmyk_profile).resolve()
    if not profile.exists():
        raise FileNotFoundError(profile)
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    definition = work / "PDFX4_poc_def.ps"
    definition.write_text(_pdfx_definition(profile, "AI Print Production OS POC"), encoding="ascii")
    output = Path(output_pdf).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        gs,
        "-dSAFER",
        "-dBATCH",
        "-dNOPAUSE",
        "-dPDFX=4",
        "-dCompatibilityLevel=1.6",
        "-dPDFACompatibilityPolicy=2",
        "-dAutoRotatePages=/None",
        "-dEmbedAllFonts=true",
        "-dEmbedSubstituteFonts=true",
        "-dSubsetFonts=true",
        "-dDetectDuplicateImages=true",
        "-dDownsampleColorImages=false",
        "-dDownsampleGrayImages=false",
        "-dDownsampleMonoImages=false",
        "-sColorConversionStrategy=CMYK",
        "-sBlendConversionStrategy=Managed",
        "-sDEVICE=pdfwrite",
        f"-sOutputICCProfile={profile}",
        f"--permit-file-read={profile}",
        f"-sOutputFile={output}",
    ]
    if font_dir:
        fonts = Path(font_dir).resolve()
        if fonts.is_dir():
            command.extend([f"-sFONTPATH={fonts}", f"--permit-file-read={fonts}/"])
    command.extend([str(definition.resolve()), str(Path(input_pdf).resolve())])
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"Ghostscript failed ({completed.returncode}): {completed.stderr or completed.stdout}")
    return {
        "output": str(output),
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "profile": str(profile),
        "warning": "PDF/X declaration is a candidate until independently validated against the target print condition.",
    }
