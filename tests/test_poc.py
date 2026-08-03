from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import pymupdf
from PIL import Image

from print_preflight.analyzer import analyze_pdf
from print_preflight.engine_worker import _parser
from print_preflight.fixer import (
    add_bleed_and_crop_marks,
    add_trim_and_crop_marks,
    export_pdfx4_cmyk,
    supports_pdfx4,
)
from print_preflight.preview import render_pdf_preview
from print_preflight.profiles import resolve_cmyk_profile
from print_preflight.rules import run_preflight
from scripts.generate_samples import make_sample


try:
    PROFILE = resolve_cmyk_profile()
except FileNotFoundError:
    PROFILE = Path("/nonexistent/print-poc-cmyk-profile.icc")


class PreflightPocTest(unittest.TestCase):
    def test_pdfx_worker_uses_python_safe_work_dir_destination(self) -> None:
        arguments = _parser().parse_args([
            "--result", "result.json", "pdfx", "input.pdf", "output.pdf", "profile.icc", "work",
        ])
        self.assertEqual(arguments.work_dir, "work")

    def test_large_format_page_uses_bounded_edge_sampling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "large-format.pdf"
            with pymupdf.open() as document:
                page = document.new_page(width=5280, height=7500)
                page.draw_rect(page.rect, color=(0.9, 0.2, 0.1), fill=(0.9, 0.2, 0.1))
                document.save(source)

            analysis = analyze_pdf(source)
            border = analysis["pages"][0]["border"]
            self.assertEqual(border["samplingMethod"], "four_edge_clips_72ppi")
            self.assertLess(border["renderedPixelCount"], 150_000)
            self.assertEqual(border["automationSafety"], "auto")

    def test_controlled_sample_and_box_fix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            boxed = root / "boxed.pdf"
            make_sample(source)
            analysis = analyze_pdf(source)
            result = run_preflight(analysis)
            codes = {issue["code"] for issue in result["issues"]}
            self.assertIn("COLOR.RGB_USED", codes)
            self.assertIn("FONT.NOT_EMBEDDED", codes)
            self.assertIn("IMAGE.LOW_EFFECTIVE_DPI", codes)
            self.assertAlmostEqual(analysis["document"]["images"][0]["minEffectiveDpi"], 84.67, places=2)
            self.assertEqual(analysis["document"]["images"][0]["placementIndex"], 1)
            self.assertIsNone(analysis["document"]["images"][0]["digestMd5"])

            add_bleed_and_crop_marks(source, boxed, analysis)
            fixed = analyze_pdf(boxed)
            self.assertTrue(fixed["pages"][0]["trimBox"]["explicit"])
            self.assertTrue(fixed["pages"][0]["bleedBox"]["explicit"])
            self.assertAlmostEqual(min(fixed["pages"][0]["bleedMargins"].values()), 3.0, places=2)

    def test_trim_only_repair_and_bounded_preview_do_not_claim_bleed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            trimmed = root / "trimmed.pdf"
            preview = root / "preview.png"
            with pymupdf.open() as document:
                page = document.new_page(width=300, height=420)
                page.draw_rect(page.rect, color=(0.2, 0.6, 0.8), fill=(0.2, 0.6, 0.8))
                document.save(source)

            add_trim_and_crop_marks(source, trimmed)
            fixed = analyze_pdf(trimmed)
            self.assertTrue(fixed["pages"][0]["trimBox"]["explicit"])
            self.assertFalse(fixed["pages"][0]["bleedBox"]["explicit"])
            self.assertIn("PAGE.BLEED_INSUFFICIENT", {item["code"] for item in run_preflight(fixed)["issues"]})

            rendered = render_pdf_preview(trimmed, preview, max_edge=640)
            self.assertTrue(preview.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertLessEqual(max(rendered["width"], rendered["height"]), 640)

    def test_trim_then_image_bleed_keeps_one_trim_and_marks_outside_three_mm_bleed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "complex.pdf"
            trimmed = root / "trimmed.pdf"
            final = root / "final.pdf"
            with pymupdf.open() as document:
                page = document.new_page(width=300, height=420)
                half_width = page.rect.width / 2
                half_height = page.rect.height / 2
                for rectangle, color in zip(
                    [
                        pymupdf.Rect(0, 0, half_width, half_height),
                        pymupdf.Rect(half_width, 0, page.rect.width, half_height),
                        pymupdf.Rect(0, half_height, half_width, page.rect.height),
                        pymupdf.Rect(half_width, half_height, page.rect.width, page.rect.height),
                    ],
                    [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0)],
                    strict=True,
                ):
                    page.draw_rect(rectangle, color=color, fill=color)
                document.save(source)

            add_trim_and_crop_marks(source, trimmed)
            trimmed_analysis = analyze_pdf(trimmed)
            result = add_bleed_and_crop_marks(trimmed, final, trimmed_analysis)
            self.assertEqual(result["pages"][0]["strategy"], "edge_pixel_mirror_extend")
            self.assertTrue(result["pages"][0]["cropMarksOutsideBleed"])

            final_analysis = analyze_pdf(final)
            page = final_analysis["pages"][0]
            self.assertAlmostEqual(page["trimBox"]["widthMm"], 300 / 72 * 25.4, places=2)
            self.assertAlmostEqual(page["trimBox"]["heightMm"], 420 / 72 * 25.4, places=2)
            self.assertTrue(all(abs(value - 3.0) < 0.01 for value in page["bleedMargins"].values()))
            self.assertNotIn("PAGE.BLEED_INSUFFICIENT", {item["code"] for item in run_preflight(final_analysis)["issues"]})

            with pymupdf.open(final) as document:
                final_page = document[0]
                bleed_render = final_page.get_pixmap(
                    matrix=pymupdf.Matrix(3, 3),
                    colorspace=pymupdf.csRGB,
                    alpha=False,
                    clip=final_page.bleedbox,
                )
            pixels = Image.frombytes("RGB", (bleed_render.width, bleed_render.height), bleed_render.samples)
            dark_pixels = sum(1 for red, green, blue in pixels.get_flattened_data() if max(red, green, blue) < 40)
            self.assertEqual(dark_pixels, 0, "No earlier crop marks may remain inside the final BleedBox")

    @unittest.skipUnless(
        shutil.which("gs") and PROFILE.exists() and supports_pdfx4(),
        "Ghostscript >= 10.07 and a CMYK profile are required for PDF/X-4 generation",
    )
    def test_pdfx_cmyk_integration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.pdf"
            boxed = root / "boxed.pdf"
            final = root / "final.pdf"
            make_sample(source)
            analysis = analyze_pdf(source)
            add_bleed_and_crop_marks(source, boxed, analysis)
            export_pdfx4_cmyk(boxed, final, PROFILE, root)
            fixed = analyze_pdf(final)
            issues = {item["code"] for item in run_preflight(fixed)["issues"]}
            self.assertNotIn("COLOR.RGB_USED", issues)
            self.assertTrue(fixed["document"]["pdfx"]["hasOutputIntent"])
            self.assertEqual(fixed["document"]["pdfx"]["declaredVersion"], "PDF/X-4")
            self.assertTrue(all(font["embedded"] for font in fixed["document"]["fonts"]))
            conversion = export_pdfx4_cmyk(boxed, root / "final-2.pdf", PROFILE, root)
            self.assertEqual(conversion["strategy"], "document_wide_icc_cmyk")
            self.assertEqual(conversion["scope"], "all_pages")
            self.assertEqual(conversion["pageCount"], 1)
            self.assertEqual(len(conversion["profileSha256"]), 64)


if __name__ == "__main__":
    unittest.main()
