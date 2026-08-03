from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image, ImageStat


PT_PER_MM = 72.0 / 25.4


def pt_to_mm(value: float) -> float:
    return round(value / PT_PER_MM, 3)


def _rect_payload(rect: pymupdf.Rect) -> dict[str, Any]:
    return {
        "points": [round(v, 3) for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
        "mm": [pt_to_mm(v) for v in (rect.x0, rect.y0, rect.x1, rect.y1)],
        "widthMm": pt_to_mm(rect.width),
        "heightMm": pt_to_mm(rect.height),
    }


def _direct_box(doc: pymupdf.Document, page: pymupdf.Page, key: str) -> bool:
    kind, _value = doc.xref_get_key(page.xref, key)
    return kind not in {"null", "none"}


def _stream_color_operators(doc: pymupdf.Document, page: pymupdf.Page) -> set[str]:
    found: set[str] = set()
    rgb_operator = re.compile(rb"(?:^|\s)(?:[-+]?\d*\.?\d+\s+){3}(?:rg|RG)(?:\s|$)")
    cmyk_operator = re.compile(rb"(?:^|\s)(?:[-+]?\d*\.?\d+\s+){4}(?:k|K)(?:\s|$)")
    gray_operator = re.compile(rb"(?:^|\s)[-+]?\d*\.?\d+\s+(?:g|G)(?:\s|$)")
    for xref in page.get_contents() or []:
        try:
            stream = doc.xref_stream(xref)
        except Exception:
            continue
        if rgb_operator.search(stream):
            found.add("DeviceRGB")
        if cmyk_operator.search(stream):
            found.add("DeviceCMYK")
        if gray_operator.search(stream):
            found.add("DeviceGray")
        for token in re.findall(rb"/(DeviceRGB|DeviceCMYK|DeviceGray|ICCBased|Separation|DeviceN|Lab)\s+(?:cs|CS)", stream):
            found.add(token.decode("ascii"))
    return found


def _document_color_tokens(doc: pymupdf.Document) -> list[str]:
    patterns = {
        "DeviceRGB": b"/DeviceRGB",
        "DeviceCMYK": b"/DeviceCMYK",
        "DeviceGray": b"/DeviceGray",
        "ICCBased": b"/ICCBased",
        "Separation": b"/Separation",
        "DeviceN": b"/DeviceN",
        "Lab": b"/Lab",
    }
    found: set[str] = set()
    for xref in range(1, doc.xref_length()):
        try:
            raw = doc.xref_object(xref, compressed=False).encode("latin-1", "ignore")
        except Exception:
            continue
        for name, token in patterns.items():
            if token in raw:
                found.add(name)
    return sorted(found)


def _font_payload(doc: pymupdf.Document, item: tuple[Any, ...]) -> dict[str, Any]:
    xref, extension, font_type, base_font, resource_name, encoding, *rest = item
    embedded = False
    extracted_bytes = 0
    if int(xref) > 0:
        try:
            _name, _ext, _type, content = doc.extract_font(int(xref))
            extracted_bytes = len(content or b"")
            embedded = extracted_bytes > 0 or str(font_type).lower() == "type3"
        except Exception:
            embedded = str(font_type).lower() == "type3"
    return {
        "xref": int(xref),
        "name": str(base_font),
        "resourceName": str(resource_name),
        "type": str(font_type),
        "encoding": str(encoding),
        "extension": str(extension),
        "embedded": embedded,
        "embeddedProgramBytes": extracted_bytes,
        "referencerXref": int(rest[0]) if rest else 0,
    }


def _image_payload(info: dict[str, Any]) -> dict[str, Any]:
    transform = list(info.get("transform") or [0, 0, 0, 0, 0, 0])
    x_axis_pt = math.hypot(float(transform[0]), float(transform[1]))
    y_axis_pt = math.hypot(float(transform[2]), float(transform[3]))
    width_px = int(info.get("width", 0))
    height_px = int(info.get("height", 0))
    dpi_x = width_px * 72.0 / x_axis_pt if x_axis_pt > 0 else 0.0
    dpi_y = height_px * 72.0 / y_axis_pt if y_axis_pt > 0 else 0.0
    bbox = pymupdf.Rect(info["bbox"])
    digest = info.get("digest")
    return {
        "xref": int(info.get("xref", 0)),
        "digestMd5": digest.hex() if isinstance(digest, bytes) else None,
        "pixelWidth": width_px,
        "pixelHeight": height_px,
        "bitsPerComponent": int(info.get("bpc", 0)),
        "colorSpace": str(info.get("cs-name", "unknown")),
        "components": int(info.get("colorspace", 0)),
        "hasMask": bool(info.get("has-mask", False)),
        "bbox": _rect_payload(bbox),
        "effectiveDpiX": round(dpi_x, 2),
        "effectiveDpiY": round(dpi_y, 2),
        "minEffectiveDpi": round(min(dpi_x, dpi_y), 2),
        "transform": [round(float(v), 4) for v in transform],
    }


def _border_classification(page: pymupdf.Page) -> dict[str, Any]:
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), alpha=False, colorspace=pymupdf.csRGB)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    band = max(2, min(5, min(image.size) // 100))
    # MuPDF may antialias the exact page boundary against white. Sampling two
    # pixels inward avoids mistaking that renderer artifact for page artwork.
    inset = 2
    pixels = []
    pixels.extend(image.crop((inset, inset, image.width - inset, inset + band)).get_flattened_data())
    pixels.extend(image.crop((inset, image.height - inset - band, image.width - inset, image.height - inset)).get_flattened_data())
    pixels.extend(image.crop((inset, inset + band, inset + band, image.height - inset - band)).get_flattened_data())
    pixels.extend(image.crop((image.width - inset - band, inset + band, image.width - inset, image.height - inset - band)).get_flattened_data())
    sample = Image.new("RGB", (len(pixels), 1))
    sample.putdata(pixels)
    stat = ImageStat.Stat(sample)
    median = tuple(int(v) for v in stat.median)
    stddev = tuple(round(v, 2) for v in stat.stddev)
    close = sum(
        1
        for p in pixels
        if max(abs(int(p[channel]) - median[channel]) for channel in range(3)) <= 8
    )
    uniform_ratio = close / len(pixels) if pixels else 0.0
    if max(stddev) <= 5 and uniform_ratio >= 0.97:
        strategy = "solid_color_extend"
        safety = "auto"
    else:
        strategy = "content_aware_or_manual"
        safety = "confirm"
    return {
        "sampledRgb": list(median),
        "channelStdDev": list(stddev),
        "uniformPixelRatio": round(uniform_ratio, 4),
        "recommendedStrategy": strategy,
        "automationSafety": safety,
    }


def analyze_pdf(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    raw = source.read_bytes()
    doc = pymupdf.open(source)
    if doc.needs_pass:
        raise ValueError("Password-protected PDFs require an explicit password workflow")

    pages: list[dict[str, Any]] = []
    document_fonts: dict[tuple[int, str], dict[str, Any]] = {}
    used_color_spaces: set[str] = set()
    all_images: list[dict[str, Any]] = []

    for page_number, page in enumerate(doc, start=1):
        font_items = []
        for item in page.get_fonts(full=True):
            payload = _font_payload(doc, item)
            font_items.append(payload)
            document_fonts[(payload["xref"], payload["name"])] = payload

        images = [_image_payload(info) for info in page.get_image_info(hashes=True, xrefs=True)]
        all_images.extend({"page": page_number, **image} for image in images)
        used_color_spaces.update(image["colorSpace"] for image in images)
        used_color_spaces.update(_stream_color_operators(doc, page))

        media = page.mediabox
        crop = page.cropbox
        trim = page.trimbox
        bleed = page.bleedbox
        trim_explicit = _direct_box(doc, page, "TrimBox")
        bleed_explicit = _direct_box(doc, page, "BleedBox")
        margins = {
            "leftMm": pt_to_mm(trim.x0 - bleed.x0) if bleed_explicit else 0.0,
            "topMm": pt_to_mm(trim.y0 - bleed.y0) if bleed_explicit else 0.0,
            "rightMm": pt_to_mm(bleed.x1 - trim.x1) if bleed_explicit else 0.0,
            "bottomMm": pt_to_mm(bleed.y1 - trim.y1) if bleed_explicit else 0.0,
        }
        pages.append(
            {
                "pageNumber": page_number,
                "rotation": int(page.rotation),
                "mediaBox": {"explicit": _direct_box(doc, page, "MediaBox"), **_rect_payload(media)},
                "cropBox": {"explicit": _direct_box(doc, page, "CropBox"), **_rect_payload(crop)},
                "trimBox": {"explicit": trim_explicit, **_rect_payload(trim)},
                "bleedBox": {"explicit": bleed_explicit, **_rect_payload(bleed)},
                "bleedMargins": margins,
                "fonts": font_items,
                "images": images,
                "border": _border_classification(page),
            }
        )

    metadata = doc.metadata or {}
    catalog = doc.pdf_catalog()
    output_intent_kind, output_intent_value = doc.xref_get_key(catalog, "OutputIntents")
    pdfx_version = metadata.get("subject", "")
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=False)
        except Exception:
            continue
        match = re.search(r"/GTS_PDFXVersion\s*\(([^)]+)\)", obj)
        if match:
            pdfx_version = match.group(1)
            break

    result = {
        "udfVersion": "0.1-poc",
        "source": {
            "fileName": source.name,
            "absolutePath": str(source),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "pdfFormat": metadata.get("format"),
            "encrypted": bool(doc.is_encrypted),
            "pageCount": doc.page_count,
        },
        "document": {
            "metadata": metadata,
            "pdfx": {
                "declaredVersion": pdfx_version or None,
                "hasOutputIntent": output_intent_kind not in {"null", "none"},
                "outputIntentReference": output_intent_value if output_intent_kind not in {"null", "none"} else None,
            },
            "colorSpaces": {
                "used": sorted(value for value in used_color_spaces if value),
                "structuralTokens": _document_color_tokens(doc),
                "confidence": {
                    "images": "high",
                    "pageOperators": "medium",
                    "structuralTokens": "low; may include unused resources",
                },
            },
            "fonts": sorted(document_fonts.values(), key=lambda item: (item["name"], item["xref"])),
            "images": all_images,
        },
        "pages": pages,
        "limitations": [
            "PDF object extraction is not semantic reconstruction of the original design tool file.",
            "Color-space operator scanning is conservative and does not replace a standards validator or RIP proof.",
            "Effective DPI is placement-dependent; rotated/sheared placements use transform-axis lengths.",
            "A missing box defaults visually in PDF readers, so explicit box presence is reported separately.",
        ],
    }
    doc.close()
    return result


def write_json(payload: dict[str, Any], output: str | Path) -> None:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
