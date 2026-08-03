from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import pymupdf

from print_preflight.analyzer import analyze_pdf
from print_preflight.fixer import add_bleed_and_crop_marks, export_pdfx4_cmyk, supports_pdfx4
from print_preflight.profiles import resolve_cmyk_profile
from print_preflight.rules import run_preflight
from scripts.generate_samples import make_sample


try:
    PROFILE = resolve_cmyk_profile()
except FileNotFoundError:
    PROFILE = Path("/nonexistent/print-poc-cmyk-profile.icc")


class PreflightPocTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
