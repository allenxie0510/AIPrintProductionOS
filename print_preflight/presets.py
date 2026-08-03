from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class PrintPreset:
    """Versioned print-condition inputs used by deterministic preflight rules."""

    preset_id: str
    version: str
    label: str
    product_type: str
    required_image_ppi: int
    bleed_mm: float
    target_pdfx: str
    color_policy: str
    status: str = "poc-only"

    def __post_init__(self) -> None:
        if not self.preset_id.strip():
            raise ValueError("preset_id is required")
        if not self.version.strip():
            raise ValueError("version is required")
        if self.required_image_ppi <= 0:
            raise ValueError("required_image_ppi must be positive")
        if self.bleed_mm < 0:
            raise ValueError("bleed_mm cannot be negative")

    def to_dict(self) -> dict[str, str | int | float]:
        payload = asdict(self)
        return {
            "presetId": payload["preset_id"],
            "version": payload["version"],
            "label": payload["label"],
            "productType": payload["product_type"],
            "requiredImagePpi": payload["required_image_ppi"],
            "bleedMm": payload["bleed_mm"],
            "targetPdfx": payload["target_pdfx"],
            "colorPolicy": payload["color_policy"],
            "status": payload["status"],
        }


DESIGNER_STANDARD_POC = PrintPreset(
    preset_id="designer-standard-poc",
    version="0.1.0",
    label="Designer standard print (POC)",
    product_type="small-format-commercial-print",
    required_image_ppi=300,
    bleed_mm=3.0,
    target_pdfx="PDF/X-4 candidate",
    color_policy="target-icc-required",
)

POSTER_POC = PrintPreset(
    preset_id="poster-poc",
    version="0.1.0",
    label="Poster (POC)",
    product_type="poster",
    required_image_ppi=150,
    bleed_mm=3.0,
    target_pdfx="PDF/X-4 candidate",
    color_policy="target-icc-required",
)

LARGE_FORMAT_POC = PrintPreset(
    preset_id="large-format-poc",
    version="0.1.0",
    label="Large format (POC)",
    product_type="large-format",
    required_image_ppi=120,
    bleed_mm=5.0,
    target_pdfx="PDF/X-4 candidate",
    color_policy="target-icc-required",
)


_PRESETS = {
    preset.preset_id: preset
    for preset in (DESIGNER_STANDARD_POC, POSTER_POC, LARGE_FORMAT_POC)
}


def available_print_presets() -> tuple[str, ...]:
    return tuple(_PRESETS)


def get_print_preset(preset_id: str) -> PrintPreset:
    try:
        return _PRESETS[preset_id]
    except KeyError as error:
        available = ", ".join(available_print_presets())
        raise ValueError(f"Unknown print preset {preset_id!r}. Available: {available}") from error
