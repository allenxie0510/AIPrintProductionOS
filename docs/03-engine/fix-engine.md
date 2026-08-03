# Fix Engine

Status: POC

## Safety Classes

- `auto`: deterministic, reversible derivative and high-confidence evidence.
- `confirm`: preview and explicit approval required.
- `manual`: engine cannot safely decide or create missing source information.

## POC Matrix

| Fix | Class | Evidence |
|---|---|---|
| Add crop marks from confirmed TrimBox | auto | Implemented |
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
