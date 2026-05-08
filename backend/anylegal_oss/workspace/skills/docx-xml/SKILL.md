---
name: docx-xml
emoji: "\U0001F527"
description: "Advanced — structural OOXML edits via run_code + lxml + zipfile. Use ONLY when the docx-editing tools (edit_document, add_comment, accept/reject, revert_edit) can't express the change. For ordinary text edits, use the docx-editing skill instead."
requires:
  tools: [read_document, run_code, list_documents]
---

# DOCX XML — Advanced Skill

You are looking at this skill because a structural edit needs raw OOXML manipulation. **Always check first whether `edit_document` can do it** — see the docx-editing skill. Only drop to `run_code` for:

- Deleting a clause **including its paragraph mark** (needs `<w:p><w:pPr><w:rPr><w:del/></w:rPr></w:pPr>` pattern)
- Inserting multi-paragraph content mid-document
- Editing a part other than `word/document.xml` (styles.xml, headers/footers, numbering.xml)
- Bulk structural rewrites spanning dozens of paragraphs

## Overview

A `.docx` file is a ZIP archive containing XML files. The main content is in `word/document.xml`. The OOXML namespace for Word is `http://schemas.openxmlformats.org/wordprocessingml/2006/main` (prefix `w:`).

**Use `language="python"` + `lxml` + `zipfile` on the XML parts directly.**

**Why NOT docx-js:** docx-js is write-only — there is no `Document.load(...)` API. It's for creating new DOCX files from scratch (the `draft` skill uses it). You cannot use it to load `Contract.docx`, mutate, and save back.

**Why NOT python-docx for run-level mutation:** python-docx silently corrupts complex legal templates. It loses non-target glyphs (other placeholders, special characters) when run.text is reassigned, has no reliable API for footnotes / bookmarks / internal hyperlinks / TableOfContents, and collapses `<w:rPr>` run properties when rewriting text — losing bold / font / size on surrounding runs. **Never use python-docx for `run.text.replace(...)` or any run-level mutation.** python-docx for *reading* and *additive* operations (adding images, adding paragraphs) is acceptable.

## The right pattern — read XML, mutate with lxml, repack with zipfile

```python
# run_code(language="python", input_files=["Contract.docx"], code=...)
import zipfile, io
from lxml import etree

NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{NS}}}"

# 1. Read document.xml from the input DOCX.
with zipfile.ZipFile('/sandbox/input/Contract.docx') as zin:
    doc_xml = zin.read('word/document.xml')
    parts = {name: zin.read(name) for name in zin.namelist()}

# 2. Mutate with lxml (example — delete a specific paragraph including its mark).
root = etree.fromstring(doc_xml)
for p in root.iter(f"{W}p"):
    text = "".join(t.text or "" for t in p.iter(f"{W}t"))
    if "text-to-delete" in text:
        p.getparent().remove(p)

# 3. Repack, preserving every other part.
parts['word/document.xml'] = etree.tostring(root, xml_declaration=True,
                                            encoding='UTF-8', standalone=True)
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
    for name, data in parts.items():
        zout.writestr(name, data)

with open('/sandbox/output/Contract_Edited.docx', 'wb') as f:
    f.write(buf.getvalue())
```

**One document = one `run_code` call.** A single call should open the file, make all changes, and save one output. Never split a document edit across multiple scripts.

## OOXML XML Reference

### Document Structure

```
word/document.xml
  <w:body>
    <w:p>                    ← paragraph
      <w:pPr>                ← paragraph properties (style, numbering, spacing)
        <w:pStyle w:val="Heading1"/>
        <w:numPr>...</w:numPr>
        <w:spacing>...</w:spacing>
        <w:ind>...</w:ind>
        <w:jc>...</w:jc>
        <w:rPr>...</w:rPr>  ← always last child of pPr
      </w:pPr>
      <w:r>                  ← run (contiguous text with same formatting)
        <w:rPr>              ← run properties (bold, italic, font, size)
          <w:b/>             ← bold
          <w:i/>             ← italic
          <w:sz w:val="24"/> ← font size in half-points (24 = 12pt)
          <w:rFonts w:ascii="Arial"/>
        </w:rPr>
        <w:t xml:space="preserve">text content</w:t>
      </w:r>
    </w:p>
```

### Schema-compliance rules

| Rule | What goes wrong if ignored |
|---|---|
| `<w:t>` with leading or trailing whitespace must carry `xml:space="preserve"` | Word strips the spaces during round-trip |
| Inside `<w:del>`, deleted text content lives in `<w:delText>`, not `<w:t>` | Tracked changes corrupt; Accept All leaves stale text |
| `<w:rPr>` is always the last child of `<w:pPr>` | Schema violation; some viewers reject the document |
| When wrapping a run in tracked-change markup, copy the original `<w:rPr>` into your `<w:ins>` / `<w:del>` runs | The change preserves bold / font / size of surrounding text |
| When creating a tracked change, replace the entire `<w:r>` element rather than injecting markup inside it | Avoids invalid run nesting and preserves Word's display logic |
| Every `w:id` in tracked changes is unique | Word silently merges or drops changes with duplicate IDs |
| `xml:space="preserve"` is the most-missed of these rules — most run-level edits need it | Spaces disappearing is invisible in source diff but obvious to the user |

### Smart quotes (typography)

DOCX documents use smart quotes stored as Unicode. When adding text via lxml, use these:

| Code | Char | Description |
|------|------|-------------|
| `‘` | ' | Left single quote |
| `’` | ' | Right single quote / apostrophe |
| `“` | " | Left double quote |
| `”` | " | Right double quote |

In lxml: `elem.text = 'Here’s a quote: “Hello”'`

### Tracked changes XML patterns

**Insertion:**
```xml
<w:ins w:id="1" w:author="Anylegal.ai" w:date="2026-05-04T00:00:00Z">
  <w:r><w:rPr>...</w:rPr><w:t>inserted text</w:t></w:r>
</w:ins>
```

**Deletion:**
```xml
<w:del w:id="2" w:author="Anylegal.ai" w:date="2026-05-04T00:00:00Z">
  <w:r><w:rPr>...</w:rPr><w:delText>deleted text</w:delText></w:r>
</w:del>
```

**Minimal edit — only mark what changes** (governing law change from Delaware to England and Wales):
```xml
<w:r><w:t>This Agreement is governed by the laws of </w:t></w:r>
<w:del w:id="1" w:author="Anylegal.ai" w:date="...">
  <w:r><w:delText>the State of Delaware</w:delText></w:r>
</w:del>
<w:ins w:id="2" w:author="Anylegal.ai" w:date="...">
  <w:r><w:t>England and Wales</w:t></w:r>
</w:ins>
<w:r><w:t>.</w:t></w:r>
```

**Deleting an entire paragraph** — mark the paragraph mark as deleted too, otherwise "Accept All" leaves an empty line:
```xml
<w:p>
  <w:pPr>
    <w:rPr>
      <w:del w:id="1" w:author="Anylegal.ai" w:date="..."/>
    </w:rPr>
  </w:pPr>
  <w:del w:id="2" w:author="Anylegal.ai" w:date="...">
    <w:r><w:delText>The deleted clause text...</w:delText></w:r>
  </w:del>
</w:p>
```

**Rejecting a counterparty's insertion** — nest your deletion inside their insertion (preserves their authorship in the audit trail):
```xml
<w:ins w:author="Counterparty" w:id="5">
  <w:del w:author="Anylegal.ai" w:id="10">
    <w:r><w:delText>their inserted text</w:delText></w:r>
  </w:del>
</w:ins>
```

**Restoring a counterparty's deletion** — add an insertion after their deletion (do not modify their deletion):
```xml
<w:del w:author="Counterparty" w:id="5">
  <w:r><w:delText>deleted text</w:delText></w:r>
</w:del>
<w:ins w:author="Anylegal.ai" w:id="10">
  <w:r><w:t>deleted text</w:t></w:r>
</w:ins>
```

### Images (additive — python-docx is acceptable here)

Inserting images is an additive operation; python-docx handles relationships and content types correctly:

```python
from docx import Document
from docx.shared import Inches, Cm

doc = Document('/sandbox/input/contract.docx')
doc.add_picture('/sandbox/input/logo.png', width=Inches(2.0))

# Or in a specific paragraph:
para = doc.paragraphs[0]
run = para.add_run()
run.add_picture('/sandbox/input/signature.png', width=Cm(5), height=Cm(2))

doc.save('/sandbox/output/contract_with_images.docx')
```

This is the **only** place python-docx is the right tool. For text mutation, always use lxml on the raw XML.

If you need raw XML control (custom positioning, wrapping):

```xml
<w:drawing>
  <wp:inline distT="0" distB="0" distL="0" distR="0">
    <wp:extent cx="914400" cy="914400"/>  <!-- EMUs: 914400 = 1 inch -->
    <wp:docPr id="1" name="Picture 1"/>
    <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
      <a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
        <pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
          <pic:blipFill>
            <a:blip r:embed="rId5"/>
          </pic:blipFill>
          <pic:spPr>
            <a:xfrm><a:ext cx="914400" cy="914400"/></a:xfrm>
          </pic:spPr>
        </pic:pic>
      </a:graphicData>
    </a:graphic>
  </wp:inline>
</w:drawing>
```

To add via raw XML you must also (1) copy the image to `word/media/`, (2) add a relationship in `word/_rels/document.xml.rels`, and (3) register the content type in `[Content_Types].xml`.

### Common pitfalls

- **Modifying during iteration**: when removing elements with lxml `findall()`, iterate over a copy: `for elem in list(body.findall(...))`.
- **Namespace-qualified attribute access**: use the full URI — `elem.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}id')`, not `elem.get('w:id')`.
- **Missing paragraph mark deletion**: if you delete all text from a paragraph but don't mark the paragraph mark as deleted, "Accept All" leaves blank lines.
- **Stale element references**: after removing/moving elements, cached references may be invalid. Re-query after structural changes.
- **ID uniqueness**: every `w:id` in tracked changes must be unique. Use `max(existing_ids) + 1`.

## Validation

When `run_code` produces a DOCX file, validate it before reporting success. The most common validation failures and their fixes:

| Failure | Fix |
|---|---|
| `<w:t>` inside `<w:del>` | Use `<w:delText>` for deleted text, not `<w:t>` |
| Missing `xml:space="preserve"` | Add the attribute to `<w:t>` elements that have leading/trailing whitespace |
| Corrupt ZIP | Ensure `zipfile.ZipFile(..., 'w')` is properly closed before reading the bytes back |
| Schema violation in `<w:pPr>` | Verify element order: `<w:pStyle>`, `<w:numPr>`, `<w:spacing>`, `<w:ind>`, `<w:jc>`, `<w:rPr>` (rPr last) |

If the script produces a corrupt DOCX, fix the Python code and retry rather than retrying the same code.

## Data + spreadsheet recipes (when run_code is the right tool for non-DOCX work)

### Generate an Excel fee schedule

```python
import openpyxl
from openpyxl.styles import Font, PatternFill

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Fee Schedule"

headers = ['Service', 'Rate (USD/hr)', 'Estimated Hours', 'Total']
for col, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col, value=header)
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="4472C4", fill_type="solid")

services = [
    ('Contract Review', 350, 8),
    ('Negotiation Support', 400, 12),
    ('Due Diligence', 375, 20),
]
for row, (service, rate, hours) in enumerate(services, 2):
    ws.cell(row=row, column=1, value=service)
    ws.cell(row=row, column=2, value=rate)
    ws.cell(row=row, column=3, value=hours)
    ws.cell(row=row, column=4, value=rate * hours)

ws.column_dimensions['A'].width = 25
wb.save('/sandbox/output/fee_schedule.xlsx')
```

### Calculate business day deadlines

```python
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

def add_business_days(start, days):
    current = start
    added = 0
    while added < days:
        current += timedelta(days=1)
        if current.weekday() < 5:
            added += 1
    return current

signing_date = datetime(2026, 5, 4)
deadlines = {
    "Signing Date": signing_date.strftime("%Y-%m-%d"),
    "Effective Date (T+5 business days)": add_business_days(signing_date, 5).strftime("%Y-%m-%d"),
    "First Payment Due (30 days)": (signing_date + timedelta(days=30)).strftime("%Y-%m-%d"),
    "Warranty Period Ends (12 months)": (signing_date + relativedelta(months=12)).strftime("%Y-%m-%d"),
}
for name, date in deadlines.items():
    print(f"{name}: {date}")
```
