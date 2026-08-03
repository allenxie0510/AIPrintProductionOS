from __future__ import annotations

from typing import Any


SEVERITY_DEDUCTION = {"FAIL": 18, "WARN": 6, "INFO": 0}


def _issue(code: str, severity: str, message: str, *, page: int | None = None, evidence: Any = None,
           auto_fix: str = "none", safety: str = "manual") -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "page": page,
        "message": message,
        "evidence": evidence,
        "fix": {"mode": auto_fix, "safety": safety},
    }


def run_preflight(analysis: dict[str, Any], required_dpi: int = 300, bleed_mm: float = 3.0) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    source = analysis["source"]
    document = analysis["document"]

    if source["encrypted"]:
        issues.append(_issue("PDF.ENCRYPTED", "FAIL", "PDF is encrypted.", auto_fix="decrypt_with_authorized_password"))

    used_spaces = set(document["colorSpaces"]["used"])
    if "DeviceRGB" in used_spaces or any("RGB" in value for value in used_spaces):
        issues.append(
            _issue(
                "COLOR.RGB_USED",
                "FAIL",
                "RGB content is used in the PDF.",
                evidence=sorted(used_spaces),
                auto_fix="icc_convert_to_target_cmyk",
                safety="review_required",
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
                auto_fix="embed_exact_font_if_available_else_substitute",
                safety="conditional",
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
                    evidence={"xref": image["xref"], "dpi": dpi, "required": required_dpi},
                    auto_fix="super_resolution_or_replace_source",
                    safety="review_required",
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
                    safety="conditional",
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
                safety="review_required",
            )
        )

    deduction = sum(SEVERITY_DEDUCTION[item["severity"]] for item in issues)
    score = max(0, 100 - deduction)
    status = "FAIL" if any(item["severity"] == "FAIL" for item in issues) else ("WARN" if issues else "PASS")
    return {
        "engineVersion": "0.1-poc",
        "status": status,
        "productionScore": score,
        "summary": {
            "fail": sum(item["severity"] == "FAIL" for item in issues),
            "warn": sum(item["severity"] == "WARN" for item in issues),
            "info": sum(item["severity"] == "INFO" for item in issues),
        },
        "policy": {"requiredImageDpi": required_dpi, "requiredBleedMm": bleed_mm},
        "issues": issues,
        "scoreDisclaimer": "POC heuristic score; not a print guarantee or industry certification.",
    }
