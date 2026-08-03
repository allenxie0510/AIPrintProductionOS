from __future__ import annotations

from dataclasses import replace
from typing import Any

from .presets import DESIGNER_STANDARD_POC, PrintPreset


SEVERITY_DEDUCTION = {"FAIL": 18, "WARN": 6, "INFO": 0}
RULE_SET_ID = "core-preflight"
RULE_SET_VERSION = "0.3.0-alpha"
RULE_VERSIONS = {
    "PDF.ENCRYPTED": "1.0.0",
    "COLOR.RGB_USED": "1.0.0",
    "FONT.NOT_EMBEDDED": "1.1.0",
    "IMAGE.LOW_EFFECTIVE_DPI": "1.2.0",
    "PAGE.TRIMBOX_MISSING": "1.0.0",
    "PAGE.BLEED_INSUFFICIENT": "1.2.0",
    "PDFX.NOT_DECLARED": "1.1.0",
}


def _rule_version(code: str) -> str:
    return RULE_VERSIONS[code]


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    page: int | None = None,
    evidence: Any = None,
    auto_fix: str = "none",
    safety: str = "manual",
    confidence: float = 1.0,
) -> dict[str, Any]:
    if safety not in {"auto", "confirm", "manual"}:
        raise ValueError(f"Invalid fix safety {safety!r}")
    return {
        "code": code,
        "ruleId": code,
        "ruleVersion": _rule_version(code),
        "severity": severity,
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "page": page,
        "message": message,
        "evidence": evidence,
        "fix": {"mode": auto_fix, "safety": safety},
    }


def _effective_preset(
    preset: PrintPreset | None,
    required_dpi: int | None,
    bleed_mm: float | None,
) -> tuple[PrintPreset, dict[str, int | float]]:
    selected = preset or DESIGNER_STANDARD_POC
    overrides: dict[str, int | float] = {}
    if required_dpi is not None:
        if required_dpi <= 0:
            raise ValueError("required_dpi must be positive")
        overrides["requiredImagePpi"] = required_dpi
        selected = replace(selected, required_image_ppi=required_dpi)
    if bleed_mm is not None:
        if bleed_mm < 0:
            raise ValueError("bleed_mm cannot be negative")
        overrides["bleedMm"] = bleed_mm
        selected = replace(selected, bleed_mm=bleed_mm)
    if overrides:
        selected = replace(
            selected,
            preset_id=f"{selected.preset_id}:runtime-override",
            version=f"{selected.version}+override",
            status="development-only",
        )
    return selected, overrides


def _rule_executions(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    severity_rank = {"PASS": 0, "INFO": 1, "WARN": 2, "FAIL": 3}
    executions = []
    for rule_id, version in RULE_VERSIONS.items():
        matches = [issue for issue in issues if issue["ruleId"] == rule_id]
        outcome = max(
            (issue["severity"] for issue in matches),
            key=lambda value: severity_rank[value],
            default="PASS",
        )
        executions.append(
            {
                "ruleId": rule_id,
                "ruleVersion": version,
                "outcome": outcome,
                "issueCount": len(matches),
            }
        )
    return executions


def run_preflight(
    analysis: dict[str, Any],
    required_dpi: int | None = None,
    bleed_mm: float | None = None,
    *,
    preset: PrintPreset | None = None,
) -> dict[str, Any]:
    selected_preset, overrides = _effective_preset(preset, required_dpi, bleed_mm)
    required_dpi = selected_preset.required_image_ppi
    bleed_mm = selected_preset.bleed_mm
    issues: list[dict[str, Any]] = []
    source = analysis["source"]
    document = analysis["document"]

    if source["encrypted"]:
        issues.append(
            _issue(
                "PDF.ENCRYPTED",
                "FAIL",
                "PDF is encrypted.",
                auto_fix="request_authorized_password_or_unencrypted_source",
                safety="manual",
            )
        )

    used_spaces = set(document["colorSpaces"]["used"])
    if "DeviceRGB" in used_spaces or any("RGB" in value for value in used_spaces):
        issues.append(
            _issue(
                "COLOR.RGB_USED",
                "FAIL",
                "RGB content is used in the PDF.",
                evidence=sorted(used_spaces),
                auto_fix="icc_convert_to_target_cmyk",
                safety="confirm",
                confidence=0.9,
            )
        )

    unembedded = [font for font in document["fonts"] if not font["embedded"]]
    for font in unembedded:
        issues.append(
            _issue(
                "FONT.NOT_EMBEDDED",
                "FAIL",
                f"Font is not embedded: {font['name']}",
                evidence={"xref": font["xref"], "type": font["type"]},
                auto_fix="embed_exact_font_if_available",
                safety="confirm",
                confidence=0.95,
            )
        )

    for image in document["images"]:
        dpi = image["minEffectiveDpi"]
        if dpi < required_dpi:
            severity = "FAIL" if dpi < 150 else "WARN"
            issues.append(
                _issue(
                    "IMAGE.LOW_EFFECTIVE_DPI",
                    severity,
                    f"Placed image effective DPI is {dpi}, below {required_dpi}.",
                    page=image["page"],
                    evidence={
                        "xref": image["xref"],
                        "dpi": dpi,
                        "required": required_dpi,
                        "placementIndex": image["placementIndex"],
                        "pixelWidth": image["pixelWidth"],
                        "pixelHeight": image["pixelHeight"],
                        "placedWidthMm": float(image["bbox"]["widthMm"]),
                        "placedHeightMm": float(image["bbox"]["heightMm"]),
                    },
                    auto_fix="super_resolution_or_replace_source",
                    safety="confirm",
                )
            )

    for page in analysis["pages"]:
        page_number = page["pageNumber"]
        if not page["trimBox"]["explicit"]:
            issues.append(
                _issue(
                    "PAGE.TRIMBOX_MISSING",
                    "FAIL",
                    "TrimBox is not explicitly defined.",
                    page=page_number,
                    auto_fix="set_trimbox_from_confirmed_page_size",
                    safety="confirm",
                )
            )
        margins = page["bleedMargins"]
        minimum = min(margins.values())
        if not page["bleedBox"]["explicit"] or minimum + 0.01 < bleed_mm:
            border = page["border"]
            issues.append(
                _issue(
                    "PAGE.BLEED_INSUFFICIENT",
                    "FAIL",
                    f"Explicit bleed of at least {bleed_mm} mm is not present on every edge.",
                    page=page_number,
                    evidence={"marginsMm": margins, "borderClassification": border},
                    auto_fix=border["recommendedStrategy"],
                    safety=border["automationSafety"],
                    confidence=border["uniformPixelRatio"],
                )
            )

    pdfx = document["pdfx"]
    if not pdfx["declaredVersion"] or not pdfx["hasOutputIntent"]:
        issues.append(
            _issue(
                "PDFX.NOT_DECLARED",
                "WARN",
                "PDF/X declaration and OutputIntent are incomplete or missing.",
                evidence=pdfx,
                auto_fix="export_pdfx_with_output_intent",
                safety="confirm",
            )
        )

    deduction = sum(SEVERITY_DEDUCTION[item["severity"]] for item in issues)
    score = max(0, 100 - deduction)
    status = "FAIL" if any(item["severity"] == "FAIL" for item in issues) else ("WARN" if issues else "PASS")
    return {
        "engineVersion": "0.2.0-alpha",
        "ruleSet": {"ruleSetId": RULE_SET_ID, "version": RULE_SET_VERSION},
        "status": status,
        "productionScore": score,
        "summary": {
            "fail": sum(item["severity"] == "FAIL" for item in issues),
            "warn": sum(item["severity"] == "WARN" for item in issues),
            "info": sum(item["severity"] == "INFO" for item in issues),
        },
        "policy": {
            "requiredImagePpi": required_dpi,
            "requiredImageDpi": required_dpi,
            "requiredBleedMm": bleed_mm,
            "printPreset": selected_preset.to_dict(),
            "runtimeOverrides": overrides,
        },
        "issues": issues,
        "ruleExecutions": _rule_executions(issues),
        "scoreDisclaimer": "POC heuristic score; not a print guarantee or industry certification.",
    }
