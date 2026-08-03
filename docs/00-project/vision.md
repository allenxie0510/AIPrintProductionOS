# Vision

Status: Accepted

## Problem

Most design tools can export PDF, but their users often do not understand bleed, effective DPI, embedded fonts, target color conditions or PDF/X. Print providers repeatedly perform manual preflight, exchange files and absorb avoidable production risk.

## Vision

AI Print Production OS turns an uploaded PDF into an explainable production decision:

```text
PDF -> Evidence -> Issues -> Safe Fix Plan -> Validated Output -> Audit Report
```

The product wins through production rules, print presets, evidence quality and trustworthy automation - not through asking an LLM to edit binary PDFs.

## Non-goals for the First Stage

- Reconstructing editable Figma, Canva or Affinity documents.
- Guaranteeing that every low-DPI image can be restored.
- Generating bleed safely for every composition.
- Replacing print-condition selection, proofing or print-provider acceptance.
