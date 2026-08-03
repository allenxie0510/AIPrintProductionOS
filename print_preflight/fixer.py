from __future__ import annotations

import io
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import NameObject, RectangleObject
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .geometry import ASPECT_RATIO_TOLERANCE, TargetGeometry
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


def _explicit_trim_or_media(page: Any) -> tuple[float, float, float, float]:
    box = page.trimbox if NameObject("/TrimBox") in page else page.mediabox
    return (float(box.left), float(box.bottom), float(box.right), float(box.top))


def _target_page_geometry(
    source_trim: tuple[float, float, float, float],
    target: TargetGeometry | None,
) -> tuple[float, float, float, float]:
    source_width = source_trim[2] - source_trim[0]
    source_height = source_trim[3] - source_trim[1]
    target_width = target.width_mm * PT_PER_MM if target else source_width
    target_height = target.height_mm * PT_PER_MM if target else source_height
    source_ratio = source_width / source_height
    target_ratio = target_width / target_height
    ratio_delta = abs(source_ratio / target_ratio - 1.0)
    if ratio_delta > ASPECT_RATIO_TOLERANCE:
        raise ValueError(
            "PDF page aspect ratio does not match the user-confirmed finished trim size."
        )
    return target_width, target_height, target_width / source_width, target_height / source_height


def _png_reader(image: Image.Image) -> ImageReader:
    payload = io.BytesIO()
    image.convert("RGB").save(payload, format="PNG")
    payload.seek(0)
    return ImageReader(payload)


def _render_clip(page: pymupdf.Page, clip: pymupdf.Rect, scale: float = 2.0) -> Image.Image:
    pixmap = page.get_pixmap(
        matrix=pymupdf.Matrix(scale, scale),
        colorspace=pymupdf.csRGB,
        alpha=False,
        clip=clip,
    )
    return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)


def _edge_bleed_overlay_page(
    input_pdf: str | Path,
    page_index: int,
    width: float,
    height: float,
    trim: tuple[float, float, float, float],
    bleed_pt: float,
):
    """Mirror only artwork edge strips into the bleed; the Trim Area stays vector and untouched."""
    with pymupdf.open(Path(input_pdf).resolve()) as document:
        source_page = document.load_page(page_index)
        source_trim = source_page.trimbox
        if source_trim.is_empty:
            source_trim = source_page.rect
        band = min(bleed_pt, source_trim.width / 2, source_trim.height / 2)
        clips = {
            "top": pymupdf.Rect(source_trim.x0, source_trim.y0, source_trim.x1, source_trim.y0 + band),
            "bottom": pymupdf.Rect(source_trim.x0, source_trim.y1 - band, source_trim.x1, source_trim.y1),
            "left": pymupdf.Rect(source_trim.x0, source_trim.y0, source_trim.x0 + band, source_trim.y1),
            "right": pymupdf.Rect(source_trim.x1 - band, source_trim.y0, source_trim.x1, source_trim.y1),
            "top_left": pymupdf.Rect(source_trim.x0, source_trim.y0, source_trim.x0 + band, source_trim.y0 + band),
            "top_right": pymupdf.Rect(source_trim.x1 - band, source_trim.y0, source_trim.x1, source_trim.y0 + band),
            "bottom_left": pymupdf.Rect(source_trim.x0, source_trim.y1 - band, source_trim.x0 + band, source_trim.y1),
            "bottom_right": pymupdf.Rect(source_trim.x1 - band, source_trim.y1 - band, source_trim.x1, source_trim.y1),
        }
        rendered = {name: _render_clip(source_page, clip) for name, clip in clips.items()}

    stream = io.BytesIO()
    c = canvas.Canvas(stream, pagesize=(width, height), pageCompression=1)
    tx0, ty0, tx1, ty1 = trim
    trim_width = tx1 - tx0
    trim_height = ty1 - ty0
    c.drawImage(_png_reader(ImageOps.flip(rendered["top"])), tx0, ty1, width=trim_width, height=bleed_pt, mask="auto")
    c.drawImage(_png_reader(ImageOps.flip(rendered["bottom"])), tx0, ty0 - bleed_pt, width=trim_width, height=bleed_pt, mask="auto")
    c.drawImage(_png_reader(ImageOps.mirror(rendered["left"])), tx0 - bleed_pt, ty0, width=bleed_pt, height=trim_height, mask="auto")
    c.drawImage(_png_reader(ImageOps.mirror(rendered["right"])), tx1, ty0, width=bleed_pt, height=trim_height, mask="auto")
    corner_positions = {
        "top_left": (tx0 - bleed_pt, ty1),
        "top_right": (tx1, ty1),
        "bottom_left": (tx0 - bleed_pt, ty0 - bleed_pt),
        "bottom_right": (tx1, ty0 - bleed_pt),
    }
    for name, (x, y) in corner_positions.items():
        corner = ImageOps.flip(ImageOps.mirror(rendered[name]))
        c.drawImage(_png_reader(corner), x, y, width=bleed_pt, height=bleed_pt, mask="auto")
    c.showPage()
    c.save()
    return PdfReader(io.BytesIO(stream.getvalue())).pages[0]


def add_trim_and_crop_marks(
    input_pdf: str | Path,
    output_pdf: str | Path,
    *,
    slug_mm: float = 8.0,
    target: TargetGeometry | None = None,
) -> dict[str, Any]:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    slug_pt = slug_mm * PT_PER_MM
    page_results = []

    for index, source_page in enumerate(reader.pages):
        source_trim = _explicit_trim_or_media(source_page)
        target_width, target_height, scale_x, scale_y = _target_page_geometry(source_trim, target)
        output_width = target_width + 2 * slug_pt
        output_height = target_height + 2 * slug_pt
        trim = (slug_pt, slug_pt, slug_pt + target_width, slug_pt + target_height)
        overlay_page = _marks_overlay_page(output_width, output_height, trim, 0.0, None)
        output_page = writer.add_blank_page(width=output_width, height=output_height)
        output_page.merge_page(overlay_page)
        source_page.cropbox = RectangleObject(list(source_trim))
        tx = slug_pt - source_trim[0] * scale_x
        ty = slug_pt - source_trim[1] * scale_y
        page_transform = Transformation(ctm=(scale_x, 0, 0, scale_y, tx, ty))
        output_page.merge_transformed_page(source_page, page_transform, over=True)
        output_page.mediabox = RectangleObject([0, 0, output_width, output_height])
        output_page.cropbox = RectangleObject([0, 0, output_width, output_height])
        output_page.trimbox = RectangleObject(list(trim))
        page_results.append({
            "page": index + 1,
            "strategy": "trim_and_crop_marks",
            "slugMm": slug_mm,
            "cropMarksAdded": True,
            "bleedGenerated": False,
            "targetWidthMm": round((trim[2] - trim[0]) / PT_PER_MM, 3),
            "targetHeightMm": round((trim[3] - trim[1]) / PT_PER_MM, 3),
            "scaleX": round(scale_x, 6),
            "scaleY": round(scale_y, 6),
        })

    output = Path(output_pdf)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        writer.write(handle)
    return {"output": str(output.resolve()), "pages": page_results}


def add_bleed_and_crop_marks(input_pdf: str | Path, output_pdf: str | Path, analysis: dict[str, Any],
                             bleed_mm: float = 3.0, slug_mm: float = 8.0,
                             target: TargetGeometry | None = None) -> dict[str, Any]:
    reader = PdfReader(str(input_pdf))
    writer = PdfWriter()
    bleed_pt = bleed_mm * PT_PER_MM
    slug_pt = slug_mm * PT_PER_MM
    page_results = []

    for index, source_page in enumerate(reader.pages):
        classification = analysis["pages"][index]["border"]
        strategy = classification["recommendedStrategy"]
        rgb = tuple(classification["sampledRgb"]) if strategy == "solid_color_extend" else None
        source_trim = _explicit_trim_or_media(source_page)
        target_width, target_height, scale_x, scale_y = _target_page_geometry(source_trim, target)
        margin = bleed_pt + slug_pt
        output_width = target_width + 2 * margin
        output_height = target_height + 2 * margin
        trim = (margin, margin, margin + target_width, margin + target_height)

        if strategy == "solid_color_extend":
            bleed_overlay = _marks_overlay_page(output_width, output_height, trim, bleed_pt, rgb)
            applied_strategy = "solid_color_extend"
            safety = "auto"
        else:
            bleed_overlay = _edge_bleed_overlay_page(
                input_pdf,
                index,
                output_width,
                output_height,
                trim,
                bleed_pt,
            )
            applied_strategy = "edge_pixel_mirror_extend"
            safety = "confirm"
        marks_overlay = _marks_overlay_page(output_width, output_height, trim, bleed_pt, None)
        output_page = writer.add_blank_page(width=output_width, height=output_height)
        output_page.merge_page(bleed_overlay)
        source_page.cropbox = RectangleObject(list(source_trim))
        tx = margin - source_trim[0] * scale_x
        ty = margin - source_trim[1] * scale_y
        page_transform = Transformation(ctm=(scale_x, 0, 0, scale_y, tx, ty))
        output_page.merge_transformed_page(source_page, page_transform, over=True)
        output_page.merge_page(marks_overlay)
        output_page.mediabox = RectangleObject([0, 0, output_width, output_height])
        output_page.cropbox = RectangleObject([0, 0, output_width, output_height])
        output_page.trimbox = RectangleObject(list(trim))
        output_page.bleedbox = RectangleObject([
            trim[0] - bleed_pt,
            trim[1] - bleed_pt,
            trim[2] + bleed_pt,
            trim[3] + bleed_pt,
        ])
        page_results.append({
            "page": index + 1,
            "strategy": applied_strategy,
            "safety": safety,
            "sampledRgb": list(rgb) if rgb is not None else None,
            "bleedMm": bleed_mm,
            "slugMm": slug_mm,
            "cropMarksAdded": True,
            "cropMarksOutsideBleed": True,
            "trimAreaPreserved": True,
            "targetWidthMm": round((trim[2] - trim[0]) / PT_PER_MM, 3),
            "targetHeightMm": round((trim[3] - trim[1]) / PT_PER_MM, 3),
            "scaleX": round(scale_x, 6),
            "scaleY": round(scale_y, 6),
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
    with profile.open("rb") as handle:
        profile_sha256 = hashlib.file_digest(handle, "sha256").hexdigest()
    page_count = len(PdfReader(str(input_pdf), strict=False).pages)
    return {
        "output": str(output),
        "strategy": "document_wide_icc_cmyk",
        "scope": "all_pages",
        "pageCount": page_count,
        "command": command,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "profile": str(profile),
        "profileSha256": profile_sha256,
        "warning": "PDF/X declaration is a candidate until independently validated against the target print condition.",
    }
