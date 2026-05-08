---
name: qa
emoji: "\u2705"
description: Quality assurance review — 6-dimension checklist covering template compliance, factual accuracy, completeness, track changes, research audit, and instruction cross-reference.
requires:
  tools: [read_document, list_documents, compare, run_code, web_search, web_fetch]
---

# Quality Assurance Review

## When to Use

Use this skill when:
- The user says /qa
- A matter is transitioning from WORKING to REVIEW
- Counsel requests a fresh QA pass after a return
- The agent has finished editing a document and needs verification

## Process

### 1. Inventory the Workspace

Call `list_documents` to see all files. Identify:
- The **primary deliverable** (the main contract/document being worked on)
- The **intake summary** (`intake_*.md`) for client instructions
- Any **playbook** files (`Playbook/*.md`, `anylegal.md`)
- Any **research notes** or **memos** created during the work
- The **original uploaded document** (if different from the deliverable)

### 2. Template Compliance Check

Read the deliverable with `read_document`. Check:
- [ ] Document structure matches the expected template format
- [ ] Clause numbering is sequential and correct
- [ ] Cross-references (to other clauses, schedules, annexes) are accurate
- [ ] Defined terms are used consistently (capitalization, spelling)
- [ ] No placeholder text remains (e.g., "[INSERT]", "TBD", "XXX")
- [ ] Standard boilerplate clauses are present (severability, governing law, etc.)

### 3. Factual Accuracy Check

Verify legal facts in the document:
- [ ] Jurisdiction references are correct for the matter type
- [ ] Legal citations (statutes, regulations, case law) are valid — use `web_search` to spot-check
- [ ] Dates, deadlines, and time periods are internally consistent
- [ ] Party names and entity types are correct throughout
- [ ] Currency and monetary amounts are consistent

### 4. Completeness Check

Read the **intake summary** and compare against the deliverable:
- [ ] All client instructions from intake have been addressed
- [ ] All documents mentioned in intake have been reviewed/incorporated
- [ ] No sections are left unfinished or contain TODO markers
- [ ] If multi-jurisdictional, all specified jurisdictions are covered

### 5. Track Changes Review

Use `run_code` (default Python) with lxml to count tracked changes (`w:ins`, `w:del`), extract authors, and assess edit scope. Then:
- [ ] Every insertion has a clear purpose (improves protection, fixes error, adds required clause)
- [ ] Every deletion is justified (removes risk, corrects error, simplifies)
- [ ] No unintended formatting-only changes
- [ ] Tracked changes are clean (no stacked/overlapping revisions)
- [ ] Total edit count is proportionate to the matter scope

### 6. Research Audit

If research notes or memos exist:
- [ ] Web sources cited are accessible and authoritative
- [ ] Citations use `[[N]](URL)` format with working URLs
- [ ] Legal positions are supported by the cited sources
- [ ] No hallucinated or outdated legal references

Use `web_search` and `web_fetch` to spot-check 2-3 key citations.

### 7. Generate QA Report

Create a `qa_<date>.md` document with:

```markdown
# QA Report — [Matter Title]

**Date:** YYYY-MM-DD
**Reviewer:** Agent QA
**Document:** [deliverable filename]

## Summary
[1-2 sentence overall assessment]

## Checklist

### Template Compliance
- [x] Structure matches template
- [x] Numbering correct
...

### Factual Accuracy
- [x] Jurisdictions correct
...

### Completeness
- [x] All client instructions addressed
...

### Track Changes
- [x] All edits justified
...

### Research Audit
- [x] Citations verified
...

## Issues Found
[List any issues, with severity: CRITICAL / WARNING / INFO]

## Verdict
[PASS / PASS WITH WARNINGS / FAIL]
```

## Guidelines

- Be thorough but proportionate — a simple NDA review needs less scrutiny than a cross-border compliance matter
- If you find CRITICAL issues, clearly flag them — these block approval
- WARNING issues should be noted but don't necessarily block approval
- Always generate the QA report even if everything passes — the report is the audit trail
- If the original document is available, use `compare` to verify the edit scope makes sense
- Do not modify the deliverable during QA — only read and report
