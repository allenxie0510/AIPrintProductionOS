from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx
import pymupdf

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

    async def test_complex_border_rejects_bleed_but_allows_honest_trim_repair(self) -> None:
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
        self.assertFalse(plan["bleed_and_crop"]["executable"])
        self.assertTrue(plan["trim_and_crop_marks"]["executable"])

        rejected = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["bleed_and_crop"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(rejected.status_code, 409, rejected.text)
        self.assertEqual(rejected.json()["error"]["code"], "FIX_ACTION_UNSAFE")

        repaired = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["trim_and_crop_marks"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(repaired.status_code, 200, repaired.text)
        after_codes = {item["code"] for item in repaired.json()["report"]["afterPreflight"]["issues"]}
        self.assertNotIn("PAGE.TRIMBOX_MISSING", after_codes)
        self.assertIn("PAGE.BLEED_INSUFFICIENT", after_codes)
        after_plan = {item["action"]: item for item in repaired.json()["report"]["fixPlan"]}
        self.assertFalse(after_plan["trim_and_crop_marks"]["executable"])

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
