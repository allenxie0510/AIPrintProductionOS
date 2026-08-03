from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

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

    async def _upload(self) -> dict:
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

        fix_response = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers=headers,
            json={"actions": ["bleed_and_crop"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(fix_response.status_code, 200, fix_response.text)
        fixed = fix_response.json()
        self.assertTrue(fixed["downloadAvailable"])
        self.assertEqual(fixed["report"]["validation"]["syntaxPassed"], True)

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
        response = await self.client.post(
            f"/v1/jobs/{created['jobId']}/fix",
            headers={"X-Job-Token": created["accessToken"]},
            json={"actions": ["pdfx_candidate"], "acknowledgeFontSubstitution": False},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "FONT_SUBSTITUTION_CONFIRMATION_REQUIRED")

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
