# PDF Parser

Status: POC

## Responsibilities

- Reject or route encrypted/unsupported inputs.
- Extract pages, boxes, images, fonts, colors and PDF/X evidence.
- Calculate placement-dependent effective DPI.
- Emit UDF observations and confidence, not production verdicts.

## POC Implementation

`print_preflight/analyzer.py` uses PyMuPDF for page geometry, fonts, color evidence and bounded edge rendering. Image placements are read from PDF content streams with pypdf, including nested Form XObjects and their transformation matrices. This avoids MuPDF display-list expansion while retaining source pixel dimensions, placed size and effective PPI evidence. qpdf provides an independent structural check.

The online adapter runs every analyze/fix stage in a separate process with configurable memory, CPU and wall-time limits. Resource exits become structured job failures instead of terminating the API process.

## Known Limits

- PDF does not retain most source-tool semantics.
- Color operators and resource tokens do not replace a standards validator or RIP.
- Inline images, unusual Form resource inheritance, transparency groups, DeviceN and malformed files need a larger regression corpus.
- PyMuPDF is process-oriented, not thread-safe for shared concurrent use.
- PyMuPDF/MuPDF licensing is an Alpha architecture gate.
