from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MIN_TRIM_MM = 10.0
MAX_TRIM_MM = 5000.0
ASPECT_RATIO_TOLERANCE = 0.02
SIZE_TOLERANCE_MM = 0.25


STANDARD_TRIM_SIZES: dict[str, tuple[str, float, float]] = {
    "business-card-cn": ("名片", 90.0, 54.0),
    "a3": ("A3", 297.0, 420.0),
    "a4": ("A4", 210.0, 297.0),
    "a5": ("A5", 148.0, 210.0),
    "b5-iso": ("B5（ISO）", 176.0, 250.0),
    "b5-jis": ("B5（JIS）", 182.0, 257.0),
}


@dataclass(frozen=True, slots=True)
class TargetGeometry:
    """User-confirmed finished trim size, independent from PDF coordinate units."""

    size_id: str
    label: str
    width_mm: float
    height_mm: float
    source: str = "user-confirmed"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.size_id.strip():
            raise ValueError("size_id is required")
        if not self.label.strip():
            raise ValueError("label is required")
        for value in (self.width_mm, self.height_mm):
            if value < MIN_TRIM_MM or value > MAX_TRIM_MM:
                raise ValueError(
                    f"Finished trim dimensions must be between {MIN_TRIM_MM:g} and {MAX_TRIM_MM:g} mm."
                )

    def to_dict(self) -> dict[str, str | float]:
        payload = asdict(self)
        return {
            "sizeId": payload["size_id"],
            "label": payload["label"],
            "widthMm": round(float(payload["width_mm"]), 3),
            "heightMm": round(float(payload["height_mm"]), 3),
            "source": payload["source"],
            "version": payload["version"],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TargetGeometry":
        return cls(
            size_id=str(payload["sizeId"]),
            label=str(payload["label"]),
            width_mm=float(payload["widthMm"]),
            height_mm=float(payload["heightMm"]),
            source=str(payload.get("source") or "user-confirmed"),
            version=str(payload.get("version") or "1.0.0"),
        )


def target_geometry(size_id: str, width_mm: float, height_mm: float) -> TargetGeometry:
    normalized_id = size_id.strip().lower()
    width = float(width_mm)
    height = float(height_mm)
    if normalized_id == "custom":
        label = "自定义"
    else:
        try:
            label, standard_width, standard_height = STANDARD_TRIM_SIZES[normalized_id]
        except KeyError as error:
            raise ValueError(f"Unknown finished trim size: {size_id!r}.") from error
        valid_orientation = (
            abs(width - standard_width) <= 0.01 and abs(height - standard_height) <= 0.01
        ) or (
            abs(width - standard_height) <= 0.01 and abs(height - standard_width) <= 0.01
        )
        if not valid_orientation:
            raise ValueError(f"{label} dimensions do not match the selected standard size.")
    return TargetGeometry(
        size_id=normalized_id,
        label=label,
        width_mm=width,
        height_mm=height,
    )


def page_geometry(page: dict[str, Any], target: TargetGeometry) -> dict[str, Any]:
    observed_box = page["trimBox"] if page["trimBox"]["explicit"] else page["mediaBox"]
    observed_width = float(observed_box["widthMm"])
    observed_height = float(observed_box["heightMm"])
    scale_x = target.width_mm / observed_width if observed_width > 0 else 0.0
    scale_y = target.height_mm / observed_height if observed_height > 0 else 0.0
    observed_ratio = observed_width / observed_height if observed_height > 0 else 0.0
    target_ratio = target.width_mm / target.height_mm
    ratio_delta = abs(observed_ratio / target_ratio - 1.0) if observed_ratio and target_ratio else 1.0
    ratio_compatible = ratio_delta <= ASPECT_RATIO_TOLERANCE
    size_matches = (
        abs(observed_width - target.width_mm) <= SIZE_TOLERANCE_MM
        and abs(observed_height - target.height_mm) <= SIZE_TOLERANCE_MM
    )
    return {
        "page": int(page["pageNumber"]),
        "observedBox": "TrimBox" if page["trimBox"]["explicit"] else "MediaBox",
        "observedWidthMm": round(observed_width, 3),
        "observedHeightMm": round(observed_height, 3),
        "targetWidthMm": round(target.width_mm, 3),
        "targetHeightMm": round(target.height_mm, 3),
        "scaleX": round(scale_x, 6),
        "scaleY": round(scale_y, 6),
        "aspectRatioDelta": round(ratio_delta, 6),
        "aspectRatioCompatible": ratio_compatible,
        "sizeMatches": size_matches,
        "measurementBasis": "user_confirmed_trim_size" if ratio_compatible else "pdf_geometry_unresolved",
    }
