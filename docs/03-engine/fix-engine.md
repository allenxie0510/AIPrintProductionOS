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
| Upload and validate exact font input | confirm | TTF/OTF signature and internal font name validated in isolated worker |
| Embed exact font | confirm | Uploaded exact fonts are supplied to PDF/X engine; end-to-end identity, license and render regression remain a release gate |
| Substitute missing font | confirm/manual | POC demonstrates why silent use is unsafe |
| PDF/X candidate | confirm | Generated; independent validation pending |
| Replace low-DPI image with higher-resolution original | confirm | Implemented by PDF image XObject reference; required pixels are calculated from placement and target PPI |
| Low-DPI super-resolution | confirm | Not implemented; original issue must remain |
| Complex photo bleed | confirm/manual | Not implemented |

## Mutation Protocol

1. Validate source hash and planned targets.
2. Write a new derivative only.
3. Record engine/tool/profile versions.
4. Re-parse and run all applicable rules.
5. Run structural validator and render diff.
6. Reject PDF/X candidates that introduce additional lower-resolution raster objects.
7. Publish result only if required gates pass; otherwise preserve the previous derivative.

## Executable-plan contract

The rule result is not itself permission to mutate a PDF. The service derives a structured `fixPlan` from the latest analysis and only accepts actions whose `executable` flag remains true when the request arrives.

- Uniform solid borders may use `bleed_and_crop`.
- Complex borders may use `trim_and_crop_marks`; the bleed issue remains open.
- Low effective PPI remains open until the user supplies a replacement image with enough source pixels. Accepted replacements preserve placement, are re-measured and update the rendered derivative preview.
- A font upload is retained only when its internal name exactly matches the missing PDF font. It is passed to the PDF/X engine through a task-scoped font path; a nonmatching or substitute font still requires explicit consent.
- Each repair starts from the current immutable derivative, writes a new intermediate file, re-analyzes the result and updates the repair history.
- Every repair history event records `resolvedIssues` from the eligible action scope. A PDF object-number change is never treated as proof that an unrelated issue was repaired.
- Crop-mark overlays contain only drawing operators; unused default font resources are stripped before merge so a geometry repair cannot create a font issue.

Source and current previews are bounded first-page PNG renders. The UI may place them in a draggable before/after comparator; the preview is evidence for review, not an independent print guarantee.
