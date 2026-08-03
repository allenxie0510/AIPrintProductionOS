# PDF Parser

Status: POC

## Responsibilities

- Reject or route encrypted/unsupported inputs.
- Extract pages, boxes, images, fonts, colors and PDF/X evidence.
- Calculate placement-dependent effective DPI.
- Emit UDF observations and confidence, not production verdicts.

## POC Implementation

`print_preflight/analyzer.py` uses PyMuPDF for high-level page/object inspection and rendering. qpdf provides an independent structural check and can become the low-level diagnostic channel.

## Known Limits

- PDF does not retain most source-tool semantics.
- Color operators and resource tokens do not replace a standards validator or RIP.
- Inline images, nested Form XObjects, transparency groups, DeviceN and malformed files need a larger regression corpus.
- PyMuPDF is process-oriented, not thread-safe for shared concurrent use.
- PyMuPDF/MuPDF licensing is an Alpha architecture gate.
