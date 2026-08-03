from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from print_preflight.analyzer import analyze_pdf
from print_preflight.geometry import TargetGeometry, target_geometry
from print_preflight.presets import DESIGNER_STANDARD_POC, PrintPreset, get_print_preset
from print_preflight.rules import RULE_VERSIONS, run_preflight
from scripts.generate_samples import make_sample


class VersionedRuleEngineTest(unittest.TestCase):
    def _analysis(self) -> dict:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        source = Path(temporary.name) / "source.pdf"
        make_sample(source)
        return analyze_pdf(source)

    def test_result_records_preset_rule_set_and_every_rule_execution(self) -> None:
        result = run_preflight(self._analysis(), preset=DESIGNER_STANDARD_POC)

        self.assertEqual(result["policy"]["printPreset"]["presetId"], "designer-standard-poc")
        self.assertEqual(result["policy"]["requiredImageDpi"], 300)
        self.assertEqual(result["ruleSet"]["ruleSetId"], "core-preflight")
        self.assertEqual(
            {execution["ruleId"] for execution in result["ruleExecutions"]},
            set(RULE_VERSIONS),
        )
        self.assertTrue(all(issue["ruleVersion"] for issue in result["issues"]))
        self.assertTrue(
            all(issue["fix"]["safety"] in {"auto", "confirm", "manual"} for issue in result["issues"])
        )

    def test_preset_threshold_changes_effective_ppi_decision(self) -> None:
        diagnostic_only = PrintPreset(
            preset_id="test-low-threshold",
            version="1.0.0",
            label="Test only",
            product_type="test",
            required_image_ppi=80,
            bleed_mm=3.0,
            target_pdfx="none",
            color_policy="diagnostic-only",
            status="test-only",
        )

        result = run_preflight(self._analysis(), preset=diagnostic_only)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertNotIn("IMAGE.LOW_EFFECTIVE_DPI", codes)
        self.assertEqual(result["policy"]["printPreset"]["version"], "1.0.0")

    def test_unknown_preset_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown print preset"):
            get_print_preset("does-not-exist")

    def test_runtime_override_cannot_reuse_original_preset_identity(self) -> None:
        result = run_preflight(self._analysis(), required_dpi=240)

        snapshot = result["policy"]["printPreset"]
        self.assertEqual(snapshot["requiredImagePpi"], 240)
        self.assertEqual(snapshot["status"], "development-only")
        self.assertTrue(snapshot["presetId"].endswith(":runtime-override"))
        self.assertTrue(snapshot["version"].endswith("+override"))

    def test_invalid_preset_threshold_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "required_image_ppi must be positive"):
            PrintPreset(
                preset_id="invalid",
                version="1",
                label="Invalid",
                product_type="test",
                required_image_ppi=0,
                bleed_mm=3.0,
                target_pdfx="none",
                color_policy="diagnostic-only",
            )

    def test_confirmed_trim_size_controls_effective_ppi_measurement(self) -> None:
        analysis = self._analysis()
        diagnostic = PrintPreset(
            preset_id="test-target-size",
            version="1.0.0",
            label="Test target size",
            product_type="test",
            required_image_ppi=100,
            bleed_mm=3.0,
            target_pdfx="none",
            color_policy="diagnostic-only",
            status="test-only",
        )
        a5 = target_geometry("a5", 148, 210)

        result = run_preflight(analysis, preset=diagnostic, target=a5)
        codes = {issue["code"] for issue in result["issues"]}

        self.assertNotIn("IMAGE.LOW_EFFECTIVE_DPI", codes)
        self.assertIn("PAGE.TARGET_SIZE_MISMATCH", codes)
        size_issue = next(issue for issue in result["issues"] if issue["code"] == "PAGE.TARGET_SIZE_MISMATCH")
        self.assertEqual(size_issue["fix"]["safety"], "confirm")
        self.assertEqual(result["policy"]["targetGeometry"]["sizeId"], "a5")

    def test_incompatible_target_aspect_ratio_is_manual(self) -> None:
        square = TargetGeometry("custom", "自定义", 210, 210)
        result = run_preflight(self._analysis(), preset=DESIGNER_STANDARD_POC, target=square)
        issue = next(item for item in result["issues"] if item["code"] == "PAGE.TARGET_SIZE_MISMATCH")

        self.assertEqual(issue["fix"]["safety"], "manual")
        self.assertFalse(issue["evidence"]["aspectRatioCompatible"])


if __name__ == "__main__":
    unittest.main()
