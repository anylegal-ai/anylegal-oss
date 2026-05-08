---
name: docx-editing
emoji: "\U0001F4DD"
description: "Edit existing DOCX files — tracked-change redlines, placeholder fills, range deletes, comments, and accept/reject finalization. Plain-text-only tools; no raw OOXML. For structural edits beyond text replacement, invoke `Skill('docx-xml')`."
requires:
  tools: [read_document, list_documents, edit_document, clone_document, add_comment, revert_edit, get_revision_stats, accept_all_changes, reject_all_changes, accept_changes, reject_changes, instantiate_template, produce_redline, compare]
---

# DOCX Editing Skill

## Tool Selection

**Author name for tracked changes:** Use the user's name from `anylegal.md` (the "About Me" section). If unknown, use `"Anylegal.ai"`.

**`edit_document` is the default tool for editing existing DOCX files.** Pass plain-text `old_text` / `new_text`; the server generates `<w:ins>` / `<w:del>` markup and preserves run properties.

| Task | Tool | Notes |
|------|------|-------|
| Change clause text (tracked) | `edit_document` | One change per call. |
| Fill a placeholder | `edit_document` | Same tool — tracked change; finalize later if user wants a clean output. |
| Delete a section | `edit_document` with `start_text` / `end_text` | Range deletion — everything between two anchors, inclusive. |
| Disambiguate duplicate text | `edit_document` + `near_text` | Picks the occurrence closest to the anchor. |
| Create a doc from a template | `instantiate_template` | Fill placeholders, save as a new file. NO tracked changes in output — produces a clean final document. The template is untouched. Name output by content (e.g. "Acme Board Resolution 2026-04-25.docx"), not "_v2". |
| Add a margin comment | `add_comment` | Handles 4-file OOXML coordination. |
| Accept all tracked changes | `accept_all_changes` | LibreOffice-backed finalization. Pass `output_path` to save as a new file. |
| Reject all tracked changes | `reject_all_changes` | LibreOffice-backed restoration. |
| Accept SPECIFIC changes by ID | `accept_changes` | Per-revision accept (lawyer-style: "accept the indemnity edits, leave the IP open"). Pair with `get_revision_stats(with_snippets=True)` to pick IDs. |
| Reject SPECIFIC changes by ID | `reject_changes` | Per-revision reject. Same workflow — get stats with snippets, pass the IDs you want to reject. |
| Revert specific edits by ID | `revert_edit` | Surgical revert of edits *we* made (from the `edit_document` response). Functionally similar to `reject_changes`; use whichever framing fits the user's ask ("undo my edit" vs. "reject the counterparty's change"). |
| Read tracked-change stats | `get_revision_stats` | Counts, authors, IDs. Pass `with_snippets=True` to also get per-revision text + context — required input for `accept_changes` / `reject_changes`. |
| Compare two documents (agent-internal diff) | `compare` | Returns structured text diff with addition/deletion counts and similarity %. Use for "what changed between v1 and v2" reasoning. For a Word-openable redlined DOCX deliverable for the user, use `produce_redline` instead. |
| Produce a redlined comparison DOCX (user-facing) | `produce_redline` | Word-openable DOCX with file2's changes shown as tracked changes against file1. LibreOffice-backed. For "show me what changed" deliverables. |
| Clone before a big edit session | `clone_document` | Optional — `edit_document` auto-clones to `_v2.docx` on first edit. Use only to pick a non-default name. |

**Rules:**
- **ONE CHANGE = ONE `edit_document` CALL.** Multiple changes → multiple calls.
- **Never use `run_code` for ordinary text edits** — even placeholder fills like `[●]` are `edit_document` cases.
- For STRUCTURAL edits the plain-text tools can't express (delete clause + paragraph mark, insert multi-paragraph content, edit styles.xml / headers / footers), invoke `Skill('docx-xml')` for the run_code + lxml + zipfile reference.
- **For creating a NEW DOCX from scratch**, invoke `Skill('draft')` instead — that skill uses docx-js for new-doc creation.

## Workflows

### Basic text replacement
```
read_document(path="Contract.docx")          → get current text
edit_document(path="Contract.docx",
              old_text="the laws of the State of Delaware",
              new_text="the laws of England and Wales",
              explanation="Change governing law")
```

Auto-clones the original to `Contract_v2.docx` on first edit. Response includes:
- `revision_ids`: list of `w:id` values for the tracked changes created
- `matched_text`: the text that was actually matched
- `context_around_edit`: surrounding text

### Range deletion (delete entire sections)
```
edit_document(path="Contract_v2.docx",
              start_text="8. NON-COMPETE", end_text="9. GOVERNING LAW",
              explanation="Remove non-compete clause")
```

### Disambiguating duplicate text
```
edit_document(path="Contract_v2.docx", old_text="written notice", new_text="prior written notice",
              near_text="termination",
              explanation="Disambiguate to the termination notice clause only")
```

### Reverting a specific change
```
revert_edit(path="Contract_v2.docx", revision_ids=[1001, 1002])
```

### Checking what's been changed
```
get_revision_stats(path="Contract_v2.docx")
```
Returns insertion/deletion counts, authors, revision IDs.

### Accept / reject finalization

Two distinct shapes, **distinct semantics**:

| Call shape | Behavior | When to use |
|---|---|---|
| `accept_all_changes(path="Contract_v2.docx", output_path="Contract_Clean.docx")` | Produces clean deliverable at `output_path`; **`Contract_v2.docx` stays editable with its tracked changes intact**. | "Send me a clean version" — you may keep iterating on v2 after. |
| `accept_all_changes(path="Contract_v2.docx")` (no `output_path`) | Mutates v2 in place, **marks v2 finalized**. Next edit on `Contract.docx` auto-clones to `Contract_v3.docx` (round-bump). | "We're done with this round — accept everything and move on." Subsequent edits start a fresh round. |
| Same shapes apply to `reject_all_changes`. | | |

Both routed through LibreOffice — handles every OOXML edge case (nested changes, paragraph marks, table cells, content controls, comment anchors). Returns `{success, path, remaining_insertions, remaining_deletions, round_finalized?}` — both counts should be 0 on success. When `round_finalized: true` appears in the response, surface this to the user (e.g. "Round 1 finalized — next edit will start v3"). The selective `accept_changes` / `reject_changes` tools are intra-round micro-edits and do **not** trigger the round-bump.

### Template fill (clean output, no tracked changes)
```
instantiate_template(
  template_path="Templates/Board_Resolution.docx",
  output_path="Acme Board Resolution 2026-04-25.docx",
  replacements={
    "[Company Name]": "Acme Corporation",
    "[Date]": "25 April 2026",
    "[Resolution Number]": "2026-001",
  },
)
```

The template is untouched. The output is a clean final document with the template's formatting preserved (run properties, paragraph styles, headers, footers all intact).

**Disambiguating repeated placeholders.** If the same token appears multiple times in the template (e.g. a generic `[●]` or `[___]` marker showing up at many fill points), each replacement key must be a unique-in-document string — include surrounding context so the matcher targets the right span. Pattern:

```
replacements={
  "Term of [●] months":      "Term of 24 months",
  "Cap of $[●]":              "Cap of $5,000,000",
  "Discount of [●] percent":  "Discount of 20 percent",
}
```

The longer key is unambiguous; identical short keys like `[●]` would only fill the first occurrence (or fail with ambiguity). For reviewable per-placeholder fills (rare — when each fill needs separate sign-off), use `clone_document` + `edit_document` per placeholder instead, then finalize with `accept_all_changes`.

### Selective accept / reject (per-change)
```
get_revision_stats(path="Contract_v2.docx", with_snippets=True)
  → {revisions: [{id: 1003, type: "insertion", author: "Counterparty",
                  text_snippet: "...sole and absolute discretion...",
                  context_around: "...the Buyer in its sole and absolute..."},
                 ...]}

accept_changes(path="Contract_v2.docx", revision_ids=[1003, 1005])
reject_changes(path="Contract_v2.docx", revision_ids=[1004])
```

Use `accept_changes` / `reject_changes` when the lawyer wants per-revision control ("accept the indemnity edits, leave the IP edits open"). Use the `_all_changes` variants for batch finalization. Both auto-clone the original to `_v2.docx` on first call so the pristine source isn't mutated.

## Verification

**Every edit operation must include verification.** Check `success: true` and inspect `context_around_edit` from the response. If the matched span looks wrong, call `read_document(path=...)` to confirm the current state before continuing.

## Anti-patterns

**Don't reach for `run_code` + python-docx for placeholder fills on existing DOCX.** Use `edit_document`, one call per placeholder. python-docx's run-level `.text.replace()` subtly corrupts complex legal templates: it strips non-target glyphs (other placeholders, special characters), collapses `<w:rPr>` run properties across runs (loses bold/font/size), and has no reliable API for footnotes, bookmarks, TableOfContents, or internal hyperlinks.

**Don't create a new DOCX in this skill.** Creation belongs in the `draft` skill — invoke `Skill('draft')`.

**Don't write lxml-based accept/reject recipes in `run_code`.** The `accept_all_changes` / `reject_all_changes` tools route through LibreOffice and handle every OOXML edge case correctly. Hand-rolled lxml accept/reject misses paragraph-mark + content-control edge cases and produces "unreadable content" dialogs in Word.
