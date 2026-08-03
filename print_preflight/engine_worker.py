from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def _positive_int_env(name: str) -> int | None:
    value = int(os.environ.get(name, "0"))
    return value if value > 0 else None


def _apply_resource_limits() -> None:
    if not sys.platform.startswith("linux"):
        return
    import resource

    memory_bytes = _positive_int_env("PRINT_MVP_ENGINE_MEMORY_BYTES")
    cpu_seconds = _positive_int_env("PRINT_MVP_ENGINE_CPU_SECONDS")
    if memory_bytes is not None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    if cpu_seconds is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))


def _write_envelope(path: Path, *, result: Any = None, error: dict[str, str] | None = None) -> None:
    path.write_text(
        json.dumps({"ok": error is None, "result": result, "error": error}, ensure_ascii=False),
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", required=True)
    subcommands = parser.add_subparsers(dest="stage", required=True)

    analyze = subcommands.add_parser("analyze")
    analyze.add_argument("input")
    analyze.add_argument("--max-pages", type=int, required=True)

    bleed = subcommands.add_parser("bleed")
    bleed.add_argument("input")
    bleed.add_argument("output")
    bleed.add_argument("analysis")
    bleed.add_argument("--bleed-mm", type=float, required=True)

    pdfx = subcommands.add_parser("pdfx")
    pdfx.add_argument("input")
    pdfx.add_argument("output")
    pdfx.add_argument("profile")
    pdfx.add_argument("work-dir")
    return parser


def main() -> int:
    args = _parser().parse_args()
    result_path = Path(args.result)
    _apply_resource_limits()
    try:
        if args.stage == "analyze":
            from .analyzer import analyze_pdf

            result = analyze_pdf(args.input, max_pages=args.max_pages)
        elif args.stage == "bleed":
            from .fixer import add_bleed_and_crop_marks

            analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
            result = add_bleed_and_crop_marks(
                args.input,
                args.output,
                analysis,
                bleed_mm=args.bleed_mm,
            )
        else:
            from .fixer import export_pdfx4_cmyk

            result = export_pdfx4_cmyk(args.input, args.output, args.profile, args.work_dir)
        _write_envelope(result_path, result=result)
        return 0
    except MemoryError:
        _write_envelope(
            result_path,
            error={
                "code": "ENGINE_RESOURCE_LIMIT",
                "message": "PDF processing exceeded the safe memory limit.",
            },
        )
        return 70
    except Exception as error:
        _write_envelope(
            result_path,
            error={
                "code": str(getattr(error, "code", "ENGINE_STAGE_FAILED")),
                "message": str(error) or error.__class__.__name__,
            },
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
