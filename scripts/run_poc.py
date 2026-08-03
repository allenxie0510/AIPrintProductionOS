from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops, ImageStat

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from print_preflight.analyzer import analyze_pdf, write_json
from print_preflight.fixer import add_bleed_and_crop_marks, export_pdfx4_cmyk
from print_preflight.rules import run_preflight
from scripts.generate_samples import make_sample


INPUT = ROOT / "tmp/pdfs/poc-input.pdf"
BOX_FIXED = ROOT / "tmp/pdfs/poc-box-fixed.pdf"
FINAL = ROOT / "output/pdf/poc-fixed-pdfx4.pdf"
OUTPUT = ROOT / "output/poc"
RENDERED = OUTPUT / "rendered"
CMYK_PROFILE = Path("/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc")


def portable_paths(value):
    """Remove workstation-specific repository prefixes from persisted evidence."""
    if isinstance(value, dict):
        return {key: portable_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [portable_paths(item) for item in value]
    if isinstance(value, str):
        prefix = str(ROOT) + "/"
        return value.replace(prefix, "")
    return value


def render_page(pdf_path: Path, output: Path, *, trim_only: bool = False, dpi: int = 150) -> None:
    doc = pymupdf.open(pdf_path)
    page = doc[0]
    clip = page.trimbox if trim_only else page.mediabox
    pix = page.get_pixmap(matrix=pymupdf.Matrix(dpi / 72, dpi / 72), clip=clip,
                          alpha=False, colorspace=pymupdf.csRGB)
    output.parent.mkdir(parents=True, exist_ok=True)
    pix.save(output)
    doc.close()


def visual_delta(before: Path, after: Path) -> dict[str, float | list[int]]:
    left = Image.open(before).convert("RGB")
    right = Image.open(after).convert("RGB")
    if left.size != right.size:
        right = right.resize(left.size, Image.Resampling.LANCZOS)
    diff = ImageChops.difference(left, right)
    stat = ImageStat.Stat(diff)
    return {
        "comparedSizePx": list(left.size),
        "meanAbsoluteChannelDelta": round(sum(stat.mean) / 3, 3),
        "maxChannelDelta": int(max(channel[1] for channel in stat.extrema)),
    }


def main() -> None:
    started = time.perf_counter()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RENDERED.mkdir(parents=True, exist_ok=True)
    make_sample(INPUT)

    input_analysis = analyze_pdf(INPUT)
    input_preflight = run_preflight(input_analysis)
    write_json(portable_paths(input_analysis), OUTPUT / "input-analysis.json")
    write_json(input_preflight, OUTPUT / "input-preflight.json")

    box_fix = add_bleed_and_crop_marks(INPUT, BOX_FIXED, input_analysis)
    pdfx_fix = export_pdfx4_cmyk(BOX_FIXED, FINAL, CMYK_PROFILE, ROOT / "tmp/pdfs")

    final_analysis = analyze_pdf(FINAL)
    final_preflight = run_preflight(final_analysis)
    write_json(portable_paths(final_analysis), OUTPUT / "final-analysis.json")
    write_json(final_preflight, OUTPUT / "final-preflight.json")

    input_render = RENDERED / "input-page.png"
    final_render = RENDERED / "final-full-page.png"
    final_trim_render = RENDERED / "final-trim-area.png"
    render_page(INPUT, input_render)
    render_page(FINAL, final_render)
    render_page(FINAL, final_trim_render, trim_only=True)

    qpdf = shutil.which("qpdf")
    check = subprocess.run([qpdf, "--check", str(FINAL)], capture_output=True, text=True) if qpdf else None
    expected_input_codes = {
        "COLOR.RGB_USED",
        "FONT.NOT_EMBEDDED",
        "IMAGE.LOW_EFFECTIVE_DPI",
        "PAGE.TRIMBOX_MISSING",
        "PAGE.BLEED_INSUFFICIENT",
        "PDFX.NOT_DECLARED",
    }
    found_input_codes = {item["code"] for item in input_preflight["issues"]}
    found_final_codes = {item["code"] for item in final_preflight["issues"]}
    final_fonts = final_analysis["document"]["fonts"]
    verification = {
        "versions": {
            "pymupdf": pymupdf.VersionBind,
            "ghostscript": subprocess.check_output(["gs", "--version"], text=True).strip(),
            "qpdf": subprocess.check_output(["qpdf", "--version"], text=True).splitlines()[0],
        },
        "inputAssertions": {
            "expectedIssuesFound": expected_input_codes.issubset(found_input_codes),
            "expectedIssueCodes": sorted(expected_input_codes),
            "actualIssueCodes": sorted(found_input_codes),
            "effectiveImageDpi": input_analysis["document"]["images"][0]["minEffectiveDpi"],
        },
        "outputAssertions": {
            "qpdfSyntaxCheckPassed": bool(check and check.returncode == 0),
            "qpdfOutput": (check.stdout + check.stderr).strip() if check else "qpdf unavailable",
            "trimBoxExplicit": all(page["trimBox"]["explicit"] for page in final_analysis["pages"]),
            "bleedBoxExplicit": all(page["bleedBox"]["explicit"] for page in final_analysis["pages"]),
            "minimumBleedMm": min(min(page["bleedMargins"].values()) for page in final_analysis["pages"]),
            "allFontsEmbedded": all(font["embedded"] for font in final_fonts),
            "usedColorSpaces": final_analysis["document"]["colorSpaces"]["used"],
            "rgbIssueCleared": "COLOR.RGB_USED" not in found_final_codes,
            "pdfxDeclared": final_analysis["document"]["pdfx"]["declaredVersion"],
            "outputIntentPresent": final_analysis["document"]["pdfx"]["hasOutputIntent"],
            "remainingIssueCodes": sorted(found_final_codes),
        },
        "visualComparison": visual_delta(input_render, final_trim_render),
        "fixEvidence": {"boxFix": box_fix, "pdfxFix": pdfx_fix},
        "elapsedSeconds": round(time.perf_counter() - started, 3),
        "result": "PASS" if all([
            expected_input_codes.issubset(found_input_codes),
            check and check.returncode == 0,
            all(page["trimBox"]["explicit"] and page["bleedBox"]["explicit"] for page in final_analysis["pages"]),
            all(font["embedded"] for font in final_fonts),
            "COLOR.RGB_USED" not in found_final_codes,
            final_analysis["document"]["pdfx"]["hasOutputIntent"],
        ]) else "PARTIAL",
        "importantBoundary": "Low image DPI intentionally remains unresolved; metadata or resampling alone cannot restore source detail.",
    }
    write_json(portable_paths(verification), OUTPUT / "verification.json")
    for intermediate in (INPUT, BOX_FIXED, ROOT / "tmp/pdfs/PDFX4_poc_def.ps"):
        intermediate.unlink(missing_ok=True)
    print(json.dumps(verification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
