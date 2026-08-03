from __future__ import annotations

import asyncio
import copy
import io
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pymupdf
from PIL import Image, ImageChops

import print_preflight.api as api_module
from print_preflight.service import PreflightService
from scripts.generate_samples import make_sample


class MvpApiTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        api_module.service = PreflightService(Path(self.temporary.name) / "data")
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api_module.app),
            base_url="http://testserver",
        )

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.temporary.cleanup()

    async def _upload(self, source: Path | None = None) -> dict:
        if source is None:
            source = Path(self.temporary.name) / "fixture.pdf"
            make_sample(source)
        response = await self.client.post(
            "/v1/jobs",
            files={"file": ("fixture.pdf", source.read_bytes(), "application/pdf")},
            data={"presetId": "designer-standard-poc"},
        )
        self.assertEqual(response.status_code, 202, response.text)
        created = response.json()
        headers = {"X-Job-Token": created["accessToken"]}
        for _attempt in range(100):
            current = await self.client.get(f"/v1/jobs/{created['jobId']}", headers=headers)
            current_payload = current.json()
            if current_payload["status"] == "failed":
                self.fail(f"analysis failed: {current_payload['error']}")
            if current_payload["status"] == "awaiting_decision":
                return created
            await asyncio.sleep(0.01)
        self.fail("analysis background task did not complete")

    async def test_upload_report_fix_download_and_delete(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}

        report_response = await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)
        self.assertEqual(report_response.status_code, 200)
        report = report_response.json()
        codes = {issue["code"] for issue in report["preflight"]["issues"]}
        self.assertIn("IMAGE.LOW_EFFECTIVE_DPI", codes)
        self.assertNotIn("absolutePath", report["analysis"]["source"])
        self.assertTrue(any(item["action"] == "bleed_and_crop" for item in report["fixPlan"]))

        preview = await self.client.get(
            f"/v1/jobs/{created['jobId']}/preview?stage=source&page=1",
            headers=headers,
        )
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertEqual(preview.headers["content-type"], "image/png")
        self.assertTrue(preview.content.startswith(b"\x89PNG\r\n\x1a\n"))

        fix_response = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["bleed_and_crop"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(fix_response.status_code, 200, fix_response.text)
        fixed = fix_response.json()
        self.assertTrue(fixed["downloadAvailable"])
        self.assertEqual(fixed["report"]["validation"]["syntaxPassed"], True)
        self.assertIn(
            "IMAGE.LOW_EFFECTIVE_DPI",
            {item["code"] for item in fixed["report"]["afterPreflight"]["issues"]},
        )

        current_preview = await self.client.get(
            f"/v1/jobs/{created['jobId']}/preview?stage=current&page=1",
            headers=headers,
        )
        self.assertEqual(current_preview.status_code, 200, current_preview.text)
        self.assertTrue(current_preview.content.startswith(b"\x89PNG\r\n\x1a\n"))

        download = await self.client.get(f"/v1/jobs/{created['jobId']}/download", headers=headers)
        self.assertEqual(download.status_code, 200)
        self.assertTrue(download.content.startswith(b"%PDF-"))

        deleted = await self.client.delete(f"/v1/jobs/{created['jobId']}/artifacts", headers=headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["deleted"], True)

        retained = api_module.service.store.get_job(created["jobId"])
        self.assertIsNone(retained["source_path"])
        self.assertIsNone(retained["output_path"])
        self.assertEqual(retained["original_name"], "deleted.pdf")
        self.assertNotIn("analysis", retained["report"])
        self.assertEqual(retained["report"]["retentionVersion"], "privacy-safe-v1")

        unavailable = await self.client.get(f"/v1/jobs/{created['jobId']}/download", headers=headers)
        self.assertEqual(unavailable.status_code, 409)

    async def test_job_token_is_required_and_not_interchangeable(self) -> None:
        created = await self._upload()
        path = f"/v1/jobs/{created['jobId']}/report"
        self.assertEqual((await self.client.get(path)).status_code, 422)
        self.assertEqual((await self.client.get(path, headers={"X-Job-Token": "wrong"})).status_code, 404)

    async def test_font_substitution_requires_explicit_confirmation(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        pdfx_action = next(item for item in report["fixPlan"] if item["action"] == "pdfx_candidate")
        response = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["pdfx_candidate"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(response.status_code, 409)
        expected = (
            "FONT_SUBSTITUTION_CONFIRMATION_REQUIRED"
            if pdfx_action["executable"]
            else "FIX_ACTION_UNSAFE"
        )
        self.assertEqual(response.json()["error"]["code"], expected)
        if pdfx_action["executable"]:
            accepted = await self.client.post(
                f"/v1/jobs/{created['jobId']}/fix",
                headers=headers,
                json={"actions": ["pdfx_candidate"], "acknowledgeFontSubstitution": True},
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            self.assertNotIn("work_dir", accepted.text)

    async def test_trim_then_complex_image_bleed_replaces_old_marks_and_preserves_trim(self) -> None:
        source = Path(self.temporary.name) / "complex-border.pdf"
        with pymupdf.open() as document:
            page = document.new_page(width=300, height=420)
            half_width = page.rect.width / 2
            half_height = page.rect.height / 2
            colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 0)]
            rectangles = [
                pymupdf.Rect(0, 0, half_width, half_height),
                pymupdf.Rect(half_width, 0, page.rect.width, half_height),
                pymupdf.Rect(0, half_height, half_width, page.rect.height),
                pymupdf.Rect(half_width, half_height, page.rect.width, page.rect.height),
            ]
            for rectangle, color in zip(rectangles, colors, strict=True):
                page.draw_rect(rectangle, color=color, fill=color)
            document.save(source)

        created = await self._upload(source)
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        plan = {item["action"]: item for item in report["fixPlan"]}
        self.assertTrue(plan["bleed_and_crop"]["executable"])
        self.assertEqual(plan["bleed_and_crop"]["safety"], "confirm")
        self.assertEqual(plan["bleed_and_crop"]["method"], "edge_pixel_mirror_extend")
        self.assertTrue(plan["trim_and_crop_marks"]["executable"])

        repaired = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["trim_and_crop_marks"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(repaired.status_code, 200, repaired.text)
        after_codes = {item["code"] for item in repaired.json()["report"]["afterPreflight"]["issues"]}
        self.assertNotIn("PAGE.TRIMBOX_MISSING", after_codes)
        self.assertIn("PAGE.BLEED_INSUFFICIENT", after_codes)
        self.assertNotIn("FONT.NOT_EMBEDDED", after_codes)
        resolved_codes = {
            item["code"]
            for item in repaired.json()["report"]["fix"]["resolvedIssues"]
        }
        self.assertEqual(resolved_codes, {"PAGE.TRIMBOX_MISSING"})
        after_plan = {item["action"]: item for item in repaired.json()["report"]["fixPlan"]}
        self.assertFalse(after_plan["trim_and_crop_marks"]["executable"])
        self.assertTrue(after_plan["bleed_and_crop"]["executable"])
        self.assertEqual(after_plan["bleed_and_crop"]["method"], "edge_pixel_mirror_extend")

        bled = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["bleed_and_crop"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(bled.status_code, 200, bled.text)
        after_bleed_codes = {item["code"] for item in bled.json()["report"]["afterPreflight"]["issues"]}
        self.assertNotIn("PAGE.BLEED_INSUFFICIENT", after_bleed_codes)
        bleed_result = bled.json()["report"]["fix"]["results"][0]["pages"][0]
        self.assertEqual(bleed_result["strategy"], "edge_pixel_mirror_extend")
        self.assertTrue(bleed_result["cropMarksOutsideBleed"])

        job_record = api_module.service.store.get_job(created["jobId"])
        with pymupdf.open(job_record["output_path"]) as document:
            final_page = document[0]
            self.assertAlmostEqual(final_page.trimbox.width, 300, places=2)
            self.assertAlmostEqual(final_page.trimbox.height, 420, places=2)

    async def test_low_resolution_image_can_be_replaced_in_place(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        issue = next(item for item in report["preflight"]["issues"] if item["code"] == "IMAGE.LOW_EFFECTIVE_DPI")
        xref = issue["evidence"]["xref"]
        self.assertEqual(issue["evidence"]["pixelWidth"], 600)
        self.assertAlmostEqual(issue["evidence"]["placedWidthMm"], 180.0, places=1)
        thumbnail = await self.client.get(
            f"/v1/jobs/{created['jobId']}/assets/image-thumbnail?xref={xref}",
            headers=headers,
        )
        self.assertEqual(thumbnail.status_code, 200, thumbnail.text)
        self.assertEqual(thumbnail.headers["content-type"], "image/png")
        self.assertTrue(thumbnail.content.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(thumbnail.content)) as rendered_thumbnail:
            self.assertLessEqual(max(rendered_thumbnail.size), 240)
        source_preview = await self.client.get(
            f"/v1/jobs/{created['jobId']}/preview?stage=source&page=1",
            headers=headers,
        )
        replacement = Path(self.temporary.name) / "replacement.png"
        Image.new("RGB", (2400, 1600), (30, 140, 210)).save(replacement)

        response = await self.client.post(
            f"/v1/jobs/{created['jobId']}/assets/image-replacement",
            headers=headers,
            files={"file": ("replacement.png", replacement.read_bytes(), "image/png")},
            data={"xref": str(xref)},
        )
        self.assertEqual(response.status_code, 200, response.text)
        remaining = response.json()["report"]["afterPreflight"]["issues"]
        self.assertFalse(
            any(item["code"] == "IMAGE.LOW_EFFECTIVE_DPI" and item["evidence"]["xref"] == xref for item in remaining)
        )
        self.assertIn("已在原版位置替换高分辨率图片", response.json()["report"]["fix"]["summary"][0])
        current_preview = await self.client.get(
            f"/v1/jobs/{created['jobId']}/preview?stage=current&page=1",
            headers=headers,
        )
        before = Image.open(io.BytesIO(source_preview.content)).convert("RGB")
        after = Image.open(io.BytesIO(current_preview.content)).convert("RGB")
        self.assertEqual(before.size, after.size)
        self.assertIsNotNone(ImageChops.difference(before, after).getbbox())

    async def test_exact_provided_fonts_remove_substitution_acknowledgement_gate(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        font_names = [
            item["name"]
            for item in report["analysis"]["document"]["fonts"]
            if not item["embedded"]
        ]
        self.assertTrue(font_names)
        report["providedFonts"] = [
            {"expectedName": name, "fontName": name, "ready": True}
            for name in font_names
        ]
        api_module.service.store.update(created["jobId"], report_json=report)
        source = Path(api_module.service.store.get_job(created["jobId"])["source_path"])
        (source.parent / "fonts").mkdir()

        def fake_export(input_pdf, output_pdf, _profile, _work_dir, *, font_dir=None):
            self.assertIsNotNone(font_dir)
            shutil.copy2(input_pdf, output_pdf)
            return {"output": str(output_pdf), "strategy": "test-exact-font-path"}

        with (
            patch("print_preflight.service.supports_pdfx4", return_value=True),
            patch("print_preflight.service.resolve_cmyk_profile", return_value=source),
            patch("print_preflight.service.export_pdfx4_cmyk_isolated", side_effect=fake_export),
        ):
            response = await self.client.post(
                f"/v1/jobs/{created['jobId']}/fix",
                headers=headers,
                json={"actions": ["pdfx_candidate"], "acknowledgeFontSubstitution": False},
            )
        self.assertEqual(response.status_code, 200, response.text)

    async def test_pdfx_quality_regression_preserves_previous_file(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        source = Path(api_module.service.store.get_job(created["jobId"])["source_path"])
        regressed = copy.deepcopy(report["analysis"])
        added = copy.deepcopy(regressed["document"]["images"][0])
        added["xref"] = 999999
        added["placementIndex"] = 999
        added["effectiveDpiX"] = 1.0
        added["effectiveDpiY"] = 1.0
        added["minEffectiveDpi"] = 1.0
        regressed["document"]["images"].append(added)

        def fake_export(input_pdf, output_pdf, _profile, _work_dir, *, font_dir=None):
            shutil.copy2(input_pdf, output_pdf)
            return {"output": str(output_pdf), "strategy": "test-regression"}

        with (
            patch("print_preflight.service.supports_pdfx4", return_value=True),
            patch("print_preflight.service.resolve_cmyk_profile", return_value=source),
            patch("print_preflight.service.export_pdfx4_cmyk_isolated", side_effect=fake_export),
            patch("print_preflight.service.analyze_pdf_isolated", return_value=regressed),
        ):
            response = await self.client.post(
                f"/v1/jobs/{created['jobId']}/fix",
                headers=headers,
                json={"actions": ["pdfx_candidate"], "acknowledgeFontSubstitution": True},
            )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["error"]["code"], "FIX_QUALITY_REGRESSION")
        current = (await self.client.get(f"/v1/jobs/{created['jobId']}", headers=headers)).json()
        self.assertEqual(current["status"], "awaiting_decision")
        self.assertFalse(current["downloadAvailable"])

    async def test_small_replacement_and_invalid_font_are_rejected(self) -> None:
        created = await self._upload()
        headers = {"X-Job-Token": created["accessToken"]}
        report = (await self.client.get(f"/v1/jobs/{created['jobId']}/report", headers=headers)).json()
        image_issue = next(item for item in report["preflight"]["issues"] if item["code"] == "IMAGE.LOW_EFFECTIVE_DPI")
        tiny = Path(self.temporary.name) / "tiny.png"
        Image.new("RGB", (100, 100), (255, 255, 255)).save(tiny)
        too_small = await self.client.post(
            f"/v1/jobs/{created['jobId']}/assets/image-replacement",
            headers=headers,
            files={"file": ("tiny.png", tiny.read_bytes(), "image/png")},
            data={"xref": str(image_issue["evidence"]["xref"])},
        )
        self.assertEqual(too_small.status_code, 422, too_small.text)
        self.assertEqual(too_small.json()["error"]["code"], "REPLACEMENT_IMAGE_TOO_SMALL")

        font_issue = next(item for item in report["preflight"]["issues"] if item["code"] == "FONT.NOT_EMBEDDED")
        invalid_font = await self.client.post(
            f"/v1/jobs/{created['jobId']}/assets/font",
            headers=headers,
            files={"file": ("font.ttf", b"not a font", "font/ttf")},
            data={"expectedName": font_issue["message"].split(": ", 1)[1]},
        )
        self.assertEqual(invalid_font.status_code, 422, invalid_font.text)

    async def test_invalid_file_and_unknown_preset_are_rejected(self) -> None:
        invalid = await self.client.post(
            "/v1/jobs",
            files={"file": ("not.pdf", b"not a pdf", "application/pdf")},
            data={"presetId": "designer-standard-poc"},
        )
        self.assertEqual(invalid.status_code, 415)

        source = Path(self.temporary.name) / "fixture.pdf"
        make_sample(source)
        unknown = await self.client.post(
            "/v1/jobs",
            files={"file": ("fixture.pdf", source.read_bytes(), "application/pdf")},
            data={"presetId": "unknown"},
        )
        self.assertEqual(unknown.status_code, 422)


if __name__ == "__main__":
    unittest.main()
