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
| Normalize whole page to user-confirmed finished Trim Size | confirm/manual | Implemented for compatible aspect ratios; incompatible ratios remain manual |
| Solid-color 3 mm bleed extension | auto | Implemented with border classifier |
| RGB -> target CMYK | confirm | Implemented with POC profile |
| Upload and validate exact font input | confirm | TTF/OTF signature and internal font name validated in isolated worker |
| Embed exact font | confirm | Uploaded exact fonts are supplied to PDF/X engine; end-to-end identity, license and render regression remain a release gate |
| Substitute missing font | confirm/manual | POC demonstrates why silent use is unsafe |
| PDF/X candidate | confirm | Generated; independent validation pending |
| Replace low-DPI image with higher-resolution original | confirm | Implemented by PDF image XObject reference; required pixels are calculated from placement and target PPI |
| Low-DPI super-resolution | confirm | Not implemented; original issue must remain |
| Complex image-edge bleed | confirm | Implemented as deterministic 3 mm edge-pixel mirror extension; Trim Area remains locked |
| Generative/content-aware bleed | confirm/manual | Not implemented |

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
- Complex image edges may use confirmed `edge_pixel_mirror_extend`. The engine samples only the inner edge bands, mirrors them into the configured bleed area, preserves the original Trim Area, and requires visual review.
- Geometry repair always normalizes from the current explicit TrimBox (or MediaBox when TrimBox is absent). Earlier slug and crop-mark content is clipped away before a new BleedBox and one crop-mark set are produced, preventing cumulative visible marks.
- Bleed fill or mirrored edge pixels are painted first, finished artwork second, and the replacement crop marks last. Crop marks are vector strokes in a Registration `/All` Separation color space whose DeviceCMYK alternate tint maps to 100% C/M/Y/K. They remain outside BleedBox and are never rasterized into the generated bleed.
- Ghostscript PDF/X export explicitly preserves Separation spaces so the Registration `/All` marks survive the later document-wide CMYK conversion.
- Geometry intent comes from the job's immutable Target Geometry, never from a guessed paper name. Compatible PDF pages are proportionally scaled to the confirmed millimetre Trim Size; a ratio difference above 2% disables both geometry and bleed automation instead of stretching artwork.
- Low effective PPI remains open until the user supplies a replacement image with enough source pixels. Accepted replacements preserve placement, are re-measured and update the rendered derivative preview.
- A font upload is retained only when its internal name exactly matches the missing PDF font. It is passed to the PDF/X engine through a task-scoped font path; a nonmatching or substitute font still requires explicit consent.
- Each repair starts from the current immutable derivative, writes a new intermediate file, re-analyzes the result and updates the repair history.
- Every repair history event records `resolvedIssues` from the eligible action scope. A PDF object-number change is never treated as proof that an unrelated issue was repaired.
- Crop-mark overlays contain only drawing operators; unused default font resources are stripped before merge so a geometry repair cannot create a font issue.

Source and current previews are bounded first-page PNG renders. The UI may place them in a draggable before/after comparator; the preview is evidence for review, not an independent print guarantee.

Low-resolution issues expose a token-protected, no-store image-XObject thumbnail plus page, placement, source pixel dimensions and placed millimetres. This ephemeral evidence is deleted with the job and is never retained as production intelligence.

CMYK conversion is document-scoped, not an image-by-image action. Ghostscript applies the selected ICC policy to all pages in one isolated run; the result records `scope=all_pages`, page count and ICC SHA-256, then the parser confirms that used RGB evidence is gone before the UI can describe the action as completed.
