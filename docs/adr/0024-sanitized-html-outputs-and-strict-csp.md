# ADR-0024: Sanitized HTML outputs and a strict Content Security Policy

**Status:** Proposed
**Date:** 2026-11-24 (record generation; the historical decision date is not established)
**Deciders:** Project maintainer

## Context

Notebook outputs can contain arbitrary HTML produced by user code or libraries.

## Decision

The SPA is served with `default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; object-src 'none'`. In the browser, `text/html` outputs pass through DOMPurify (no scripts, frames or forms) and are mounted in a Shadow DOM; Markdown and ANSI outputs are sanitized too. HTML exports are sanitized server-side with nh3 and carry their own CSP.

**Rationale:** The code states that `'unsafe-inline'` styles are needed for CodeMirror runtime styles and `<style>` inside the Shadow DOM of HTML outputs.

## Alternatives Considered

Not identified in the analyzed material.

## Consequences

The items below are an analysis of the current code, not a historical record.

### Positive

- Untrusted output cannot run scripts in the app origin.

### Negative

- Interactive HTML widgets that need JavaScript do not work.

### Risks

- Inline styles remain allowed.

## Validation

- **Evidence in code:** `backend/src/notisbook/static.py`, `frontend/src/components/outputs/purify.ts`, `frontend/src/components/outputs/HtmlOutput.tsx`, `backend/src/notisbook/export/html_report.py`
- **How to confirm:** `grep -n 'default-src' backend/src/notisbook/static.py`

## Implementation Notes

No further notes.

---

**Author:** Romerito Morais

**Version:** 20261124164049

**Date:** 2026-11-24 16:40:49

**SKILL:** Document
