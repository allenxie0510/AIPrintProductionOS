from __future__ import annotations

import argparse
import json

from .analyzer import analyze_pdf, write_json
from .fixer import add_bleed_and_crop_marks
from .presets import DESIGNER_STANDARD_POC, available_print_presets, get_print_preset
from .rules import run_preflight


def main() -> None:
    parser = argparse.ArgumentParser(description="PDF print preflight proof of concept")
    subparsers = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = subparsers.add_parser("analyze")
    analyze_cmd.add_argument("input")
    analyze_cmd.add_argument("--output", required=True)

    preflight_cmd = subparsers.add_parser("preflight")
    preflight_cmd.add_argument("input")
    preflight_cmd.add_argument("--output", required=True)
    preflight_cmd.add_argument(
        "--preset",
        choices=available_print_presets(),
        default=DESIGNER_STANDARD_POC.preset_id,
    )

    fix_cmd = subparsers.add_parser("fix-boxes")
    fix_cmd.add_argument("input")
    fix_cmd.add_argument("output")
    fix_cmd.add_argument("--bleed-mm", type=float, default=3.0)

    args = parser.parse_args()
    analysis = analyze_pdf(args.input)
    if args.command == "analyze":
        write_json(analysis, args.output)
    elif args.command == "preflight":
        write_json(run_preflight(analysis, preset=get_print_preset(args.preset)), args.output)
    elif args.command == "fix-boxes":
        result = add_bleed_and_crop_marks(args.input, args.output, analysis, bleed_mm=args.bleed_mm)
        print(json.dumps(result, ensure_ascii=False, indent=2))
