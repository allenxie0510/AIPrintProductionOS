from __future__ import annotations

import os
from pathlib import Path


CMYK_PROFILE_ENV = "PRINT_POC_CMYK_PROFILE"


def resolve_cmyk_profile(explicit: str | Path | None = None) -> Path:
    configured = explicit or os.environ.get(CMYK_PROFILE_ENV)
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path("/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc"),
        Path("/usr/share/color/icc/ghostscript/default_cmyk.icc"),
        Path("/usr/share/color/icc/ghostscript/ps_cmyk.icc"),
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        f"No CMYK ICC profile found. Set {CMYK_PROFILE_ENV} to a readable CMYK ICC profile."
    )
