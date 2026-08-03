# Fix Engine

Status: Alpha MVP

## Safety Classes

- `auto`: deterministic, reversible derivative and high-confidence evidence.
- `confirm`: preview and explicit approval required.
- `manual`: engine cannot safely decide or create missing source information.

## POC Matrix

| Fix | Class | Evidence |
|---|---|---|
| Add explicit TrimBox, slug and crop marks without claiming bleed | confirm | Implemented |
| Solid-color 3 mm bleed extension | auto | Implemented with border classifier |
| RGB -> target CMYK | confirm | Implemented with POC profile |
| Embed exact font | confirm | Engine path proven; exact font not proven |
| Substitute missing font | confirm/manual | POC demonstrates why silent use is unsafe |
| PDF/X candidate | confirm | Generated; independent validation pending |
| Low-DPI super-resolution | confirm | Not implemented; original issue must remain |
| Complex photo bleed | confirm/manual | Not implemented |

## Mutation Protocol

1. Validate source hash and planned targets.
2. Write a new derivative only.
3. Record engine/tool/profile versions.
4. Re-parse and run all applicable rules.
5. Run structural validator and render diff.
6. Publish result only if required gates pass; otherwise preserve as failed attempt.

## Executable-plan contract

The rule result is not itself permission to mutate a PDF. The service derives a structured `fixPlan` from the latest analysis and only accepts actions whose `executable` flag remains true when the request arrives.

- Uniform solid borders may use `bleed_and_crop`.
- Complex borders may use `trim_and_crop_marks`; the bleed issue remains open.
- Low effective PPI remains open until a higher-quality source or a separately approved enhancement workflow exists.
- Each repair starts from the current immutable derivative, writes a new intermediate file, re-analyzes the result and updates the repair history.

Source and current previews are bounded first-page PNG renders. The UI may place them in a draggable before/after comparator; the preview is evidence for review, not an independent print guarantee.
