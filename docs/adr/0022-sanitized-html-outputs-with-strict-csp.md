# ADR-0022: Sanitized HTML outputs with a strict CSP

**Status:** Proposed
**Date:** 2026-11-23 (record generation date; historical date not proven)
**Deciders:** Not identified in the analyzed material

## Context
Notebook outputs may contain arbitrary HTML that could run scripts in the app origin.

## Decision
The SPA is served with `script-src 'self'`, `frame-ancestors 'none'` and `object-src 'none'`; the UI does not render JavaScript or ipywidgets outputs and sanitizes Markdown with DOMPurify. The HTML export sanitizes outputs with `nh3`, contains no JavaScript and is served with `CSP: sandbox`.

Historical rationale not recovered from the code.

## Alternatives Considered
Not identified in the analyzed material.

## Consequences

> Current analysis based on the code; not a historical record of the decision.

### Positive
- Outputs cannot execute code in the app or in exported reports.

### Negative
- Interactive outputs (JavaScript, widgets) are not supported.

### Risks
- Inline styles are allowed (`style-src 'unsafe-inline'`).

## Validation
- **Evidence in the code:** `backend/src/notisbook/static.py`, `backend/src/notisbook/export/html_report.py`, `frontend/src/components/outputs/mime.ts`
- **How to confirm:** read the files above in the repository.

## Implementation Notes
Fonts are bundled locally because the CSP blocks external sources.

---

**Author:** Romerito Morais

**Version:** 20261123205814

**Date:** 2026-11-23 20:58:14

**SKILL:** Document
