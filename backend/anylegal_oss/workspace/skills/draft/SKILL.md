---
name: draft
emoji: "\U0001F4DD"
description: Draft a NEW document from scratch via docx-js (run_code language="node"). Use when the user wants to create new legal content from a blank page — agreements, memos, letters, resolutions, term sheets. For filling an existing template with placeholder values, use the `docx-editing` skill instead.
requires:
  tools: [run_code, list_documents, todo_write]
---

# Document Drafting (docx-js, from-scratch only)

## When to Use

Use this skill when:
- The user asks to draft a new document, clause, or section from scratch
- The user says /draft
- The user asks to "create", "write", "generate", or "prepare" legal content

**Do NOT use this skill for:**
- Filling placeholders in an existing template (e.g. `[Disclosing Party]` → `Acme Corp`) — that is an edit task. Invoke `Skill(skill="docx-editing")` and use `instantiate_template` (or `edit_document` for per-placeholder review).
- Editing or restructuring an existing DOCX — also `docx-editing`.

## Critical rules (read first)

These rules constrain how you call the tool. Following them produces documents that open cleanly in Word, Google Docs, and LibreOffice; ignoring them produces invalid output.

| # | Rule | Why |
|---|---|---|
| 1 | **DOCX creation goes through `run_code(language="node")` calling docx-js.** Not python-docx. Not pandoc. Not lxml. | docx-js is the only library with reliable APIs for footnotes, internal hyperlinks, TableOfContents, page numbers in headers/footers, and positional tabs. |
| 2 | **One document = one `run_code(language="node")` call.** Write the complete document in a single call — no skeleton-then-fill, no part-by-part assembly. | docx-js has no `Document.load()` API; a second call to the same filename silently overwrites the first. |
| 3 | **Bullets are produced via numbering config, not inline characters.** Never write `new TextRun("• Item")` — use `LevelFormat.BULLET` with a `numbering` block on the Document. See "Lists" below. | Inline bullet glyphs render inconsistently across viewers and break list semantics. |
| 4 | **Filenames must be distinct logical names.** Avoid `_Part1` / `_Final` / `_Draft` / `_v2` / `_Copy` suffixes. One logical document = one filename. | Versioning suffixes signal split-document anti-patterns and confuse downstream document management. |
| 5 | **Multi-document sets: `todo_write` first.** If the user asks for a "set" / "series" / "package", your first tool call is `todo_write` with one item per document. After each document is saved, mark it completed and continue with the next item — in the same turn. | Without an explicit todo list, multi-doc requests get partially completed and abandoned. |
| 6 | **Content completeness.** The saved document must be complete, not a skeleton: schedules referenced in the body must exist, defined terms must appear in the definitions clause, both parties' signature blocks for agreements, witness blocks for deeds. | A skeleton wastes the user's time — they have to ask again to fill the gaps. |

Data prep in Python is fine (pandas, openpyxl). Do it in a separate `run_code(language="python")` call that writes JSON to `/sandbox/output/*.json`, then consume that JSON from a `run_code(language="node")` call. Do NOT spawn Node as a subprocess from Python.

## Process

1. **Understand the request:**
   - What type of document or clause?
   - Which jurisdiction and governing law?
   - Which party does the user represent?
   - Any specific requirements or constraints?
2. **Check playbook** — if available in context, apply the user's preferred positions and risk posture.
3. **Multi-document sets — pre-flight `todo_write`:**
   - If the user asks for a "set" / "series" / "package" (e.g. "Singapore Pte Ltd document set", "incorporation pack", "full SPA suite"), your first substantive tool call is `todo_write` listing one item per document.
   - Example: `[{"content": "Draft Company Constitution", ...}, {"content": "Draft Director Appointment Resolution", ...}, ...]`.
   - After each document is saved, call `todo_write` again marking the completed item and the next one in_progress.
   - Do not start `run_code` to create any document until the todo list is written.
   - Complete every document in the same turn. Don't stop mid-series.
4. **One document per `run_code` call.** Never split a document across multiple calls.

## Sandbox preconditions (trust these, don't probe)

- `docx` (docx-js v9.5.1) is globally installed in the Node sandbox. Do not probe with `npm list docx`, `subprocess.run`, or similar — just `require('docx')`.
- Write outputs to `/sandbox/output/<filename>.docx`. That directory is where the backend imports from.
- `Packer.toBuffer(doc)` returns a Promise. Either `await` it or use `.then(buf => ...)`. Writing the un-awaited Promise with `fs.writeFileSync` throws `ERR_INVALID_ARG_TYPE`.

## Canonical docx-js invocation

```javascript
// run_code(language="node", code=...)
const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
        FootnoteReferenceRun, Bookmark } = require('docx');
const fs = require('fs');

const doc = new Document({
  creator: "Anylegal.ai",
  styles: {
    default: { document: { run: { font: "Times New Roman", size: 24 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal",
        quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } },
    ]
  },
  footnotes: {
    1: { children: [new Paragraph("Source: Companies Act 2006 (UK), s. 172")] },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },  // US Letter. A4 = 11906 × 16838.
        margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 },
      },
    },
    children: [
      new Paragraph({
        heading: HeadingLevel.HEADING_1,
        children: [new Bookmark({ id: "preamble", children: [new TextRun("1. PREAMBLE")] })],
      }),
      new Paragraph({
        alignment: AlignmentType.JUSTIFIED,
        children: [
          new TextRun("This Agreement is dated "),
          new TextRun({ text: "15 May 2026", bold: true }),
          new TextRun(" pursuant to Section 172"),
          new FootnoteReferenceRun(1),
          new TextRun(" of the Companies Act."),
        ],
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("/sandbox/output/Agreement.docx", buf);
  console.log("ok");
});
```

---

#### docx-js creation reference

##### Setup — all the imports you'll likely need

```javascript
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
        Header, Footer, AlignmentType, PageOrientation, LevelFormat, ExternalHyperlink,
        InternalHyperlink, Bookmark, FootnoteReferenceRun, PositionalTab,
        PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
        TabStopType, TabStopPosition, Column, SectionType,
        TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
        VerticalAlign, PageNumber, PageBreak } = require('docx');

const doc = new Document({ sections: [{ children: [/* content */] }] });
Packer.toBuffer(doc).then(buffer => fs.writeFileSync("/sandbox/output/doc.docx", buffer));
```

##### Page size

```javascript
// docx-js defaults to A4. For US documents, set US Letter explicitly.
sections: [{
  properties: {
    page: {
      size: {
        width: 12240,   // 8.5 inches in DXA
        height: 15840   // 11 inches in DXA
      },
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } // 1 inch margins
    }
  },
  children: [/* content */]
}]
```

**Common page sizes (DXA units, 1440 DXA = 1 inch):**

| Paper | Width | Height | Content Width (1" margins) |
|-------|-------|--------|---------------------------|
| US Letter | 12,240 | 15,840 | 9,360 |
| A4 (default) | 11,906 | 16,838 | 9,026 |

**Landscape orientation:** docx-js swaps width/height internally — pass portrait dimensions and let it handle the swap:
```javascript
size: {
  width: 12240,   // Pass SHORT edge as width
  height: 15840,  // Pass LONG edge as height
  orientation: PageOrientation.LANDSCAPE  // docx-js swaps them in the XML
}
// Content width = 15840 - left margin - right margin (uses the long edge)
```

##### Styles (override built-in headings)

Default to Arial — it renders consistently across Word, Google Docs, and LibreOffice. Headings stay in standard black; coloured headings rarely improve readability and often look amateurish in legal documents.

```javascript
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } }, // 12pt default
    paragraphStyles: [
      // Use exact IDs to override built-in styles
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } }, // outlineLevel required for TOC
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    children: [
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Recitals")] }),
    ]
  }]
});
```

##### Lists — bullets via numbering config

Bullet glyphs in `TextRun` content render inconsistently and break list semantics. Use a `numbering` config block on the Document and reference it from each list paragraph.

```javascript
// ❌ Avoid
new Paragraph({ children: [new TextRun("• Item")] })  // glyph in text — bad

// ✅ Use numbering config
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    children: [
      new Paragraph({ numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("Confidentiality obligation")] }),
      new Paragraph({ numbering: { reference: "numbers", level: 0 },
        children: [new TextRun("Definitions")] }),
    ]
  }]
});

// Each reference creates an independent numbering sequence:
//   Same reference reused = continues (1, 2, 3 then 4, 5, 6)
//   Different reference = restarts (1, 2, 3 then 1, 2, 3)
```

##### Tables

Tables need both `columnWidths` on the table and `width` on each cell. Without both, layout breaks on some viewers.

```javascript
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

new Table({
  width: { size: 9360, type: WidthType.DXA }, // Use DXA — percentages break in Google Docs
  columnWidths: [4680, 4680], // Must sum to table width (DXA: 1440 = 1 inch)
  rows: [
    new TableRow({
      children: [
        new TableCell({
          borders,
          width: { size: 4680, type: WidthType.DXA }, // Match the columnWidth
          shading: { fill: "D5E8F0", type: ShadingType.CLEAR }, // CLEAR — SOLID renders as black
          margins: { top: 80, bottom: 80, left: 120, right: 120 }, // Internal padding (does not add to width)
          children: [new Paragraph({ children: [new TextRun("Cell")] })]
        })
      ]
    })
  ]
})
```

**Table width calculation:**

Always use `WidthType.DXA` (`WidthType.PERCENTAGE` is incompatible with Google Docs).

```javascript
// Table width = sum of columnWidths = content width
// US Letter with 1" margins: 12240 - 2880 = 9360 DXA
width: { size: 9360, type: WidthType.DXA },
columnWidths: [7000, 2360]  // Must sum to table width
```

**Width rules:**
- Always use `WidthType.DXA` (never `WidthType.PERCENTAGE`)
- Table width must equal the sum of `columnWidths`
- Cell `width` must match its corresponding `columnWidth`
- Cell `margins` are internal padding — they reduce content area, not add to cell width
- For full-width tables, use the content width (page width minus left and right margins)

##### Images

```javascript
new Paragraph({
  children: [new ImageRun({
    type: "png", // Required: png, jpg, jpeg, gif, bmp, svg
    data: fs.readFileSync("/sandbox/input/image.png"),
    transformation: { width: 200, height: 150 },
    altText: { title: "Title", description: "Desc", name: "Name" } // All three required
  })]
})
```

##### Page breaks

```javascript
// PageBreak must live inside a Paragraph — standalone produces invalid XML
new Paragraph({ children: [new PageBreak()] })

// Or use pageBreakBefore
new Paragraph({ pageBreakBefore: true, children: [new TextRun("New page")] })
```

##### Hyperlinks

```javascript
// External link
new Paragraph({
  children: [new ExternalHyperlink({
    children: [new TextRun({ text: "Click here", style: "Hyperlink" })],
    link: "https://example.com",
  })]
})

// Internal link (bookmark + reference)
// 1. Create bookmark at destination
new Paragraph({ heading: HeadingLevel.HEADING_1, children: [
  new Bookmark({ id: "schedule_a", children: [new TextRun("Schedule A")] }),
]})
// 2. Link to it
new Paragraph({ children: [new InternalHyperlink({
  children: [new TextRun({ text: "See Schedule A", style: "Hyperlink" })],
  anchor: "schedule_a",
})]})
```

##### Footnotes

```javascript
const doc = new Document({
  footnotes: {
    1: { children: [new Paragraph("Source: Annual Report 2025")] },
    2: { children: [new Paragraph("See Schedule B for methodology")] },
  },
  sections: [{
    children: [new Paragraph({
      children: [
        new TextRun("Net revenue grew 15%"),
        new FootnoteReferenceRun(1),
        new TextRun(" using adjusted metrics"),
        new FootnoteReferenceRun(2),
      ],
    })]
  }]
});
```

##### Tab stops

```javascript
// Right-align text on the same line (e.g., date opposite a title)
new Paragraph({
  children: [
    new TextRun("Company Name"),
    new TextRun("\tJanuary 2026"),
  ],
  tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
})

// Dot leader (e.g., TOC-style)
new Paragraph({
  children: [
    new TextRun("Introduction"),
    new TextRun({ children: [
      new PositionalTab({
        alignment: PositionalTabAlignment.RIGHT,
        relativeTo: PositionalTabRelativeTo.MARGIN,
        leader: PositionalTabLeader.DOT,
      }),
      "3",
    ]}),
  ],
})
```

##### Multi-column layouts

```javascript
// Equal-width columns
sections: [{
  properties: {
    column: {
      count: 2,          // number of columns
      space: 720,        // gap between columns in DXA (720 = 0.5 inch)
      equalWidth: true,
      separate: true,    // vertical line between columns
    },
  },
  children: [/* content flows naturally across columns */]
}]

// Custom-width columns (equalWidth must be false)
sections: [{
  properties: {
    column: {
      equalWidth: false,
      children: [
        new Column({ width: 5400, space: 720 }),
        new Column({ width: 3240 }),
      ],
    },
  },
  children: [/* content */]
}]
```

Force a column break with a new section using `type: SectionType.NEXT_COLUMN`.

##### Table of Contents

```javascript
// Headings must use HeadingLevel directly — no custom styles for TOC entries
new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" })
```

The TOC must be a `new TableOfContents(...)` object — not a plain heading. A `Paragraph({ text: "Table of Contents" })` (or that text wrapped in a `HEADING_1`) produces a static label without a Word field, so "Update Field" in Word does nothing. When the user asks for a TOC, instantiate the class and add it to the section's `children` array before the headings it should index.

##### Headers / footers

```javascript
sections: [{
  properties: {
    page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } // 1440 = 1 inch
  },
  headers: {
    default: new Header({ children: [new Paragraph({ children: [new TextRun("Header")] })] })
  },
  footers: {
    default: new Footer({ children: [new Paragraph({
      children: [new TextRun("Page "), new TextRun({ children: [PageNumber.CURRENT] })]
    })] })
  },
  children: [/* content */]
}]
```

##### Quick reference — docx-js gotchas

A summary of the rules above, ordered by frequency of impact:

1. **Page size** — set explicitly (docx-js defaults to A4)
2. **Landscape** — pass portrait dimensions; orientation flag swaps internally
3. **Bullets** — numbering config, never inline glyphs
4. **PageBreak** — must be inside a Paragraph
5. **ImageRun** — `type` parameter is required
6. **Tables** — `width` (DXA) on the table AND on each cell
7. **Cell margins** — set them; otherwise the table looks cramped
8. **Shading** — use `ShadingType.CLEAR` (SOLID renders black on some viewers)
9. **Tables aren't dividers** — use a Paragraph with a bottom border
10. **TOC** — instantiate `TableOfContents`, do not write a plain heading
11. **TOC headings** — use `HeadingLevel.*` only, no custom paragraph styles
12. **Override built-in styles** — exact IDs ("Heading1", "Heading2", etc.)
13. **`outlineLevel`** — required on heading paragraphs (0 for H1, 1 for H2, etc.) for TOC to populate
14. **No `\n`** — use separate Paragraph elements for line breaks

#### Reminders

**One document, one call — context.** docx-js has no reader API; a second call to the same filename overwrites the first. Modern models emit 15–32K output tokens per turn — a full SSA is ~8–12K tokens of final text. It fits. Write it all in one call. If a monolith truly exceeds one call, split into separate logical documents (e.g. "Shareholders Agreement" + "Side Letter"), not parts of one file.

**Filenames for multi-doc deliverables.** Use descriptive distinct names: `1_Term_Sheet.docx`, `2_Share_Subscription_Agreement.docx`, `3_Shareholders_Agreement.docx`. Avoid `_Part1` / `_Final` / `_v2` / `_Draft` / `_Copy`.

**Editing is a different skill.** If the user asks to revise a clause, fill template placeholders, or add tracked changes — that's not drafting. Invoke `Skill(skill="docx-editing")` and use `instantiate_template` (template fills) or `edit_document` (redline edits).

### Content completeness

The final saved document must be complete, not a skeleton:

- Every Schedule/Annex referenced in the body exists (even with `[DETAILS]` placeholders)
- Every defined term in quotes appears in the Definitions clause
- Standard boilerplate: Notices, Severability, Waiver, Counterparts, Entire Agreement, Amendment, Governing Law
- Agreements: both parties' signature blocks. Deeds: witness blocks under each signatory.

## Output Format

- **Brief explanation** of structure and key decisions
- **The drafted content** (created as a document in the workspace)
- **Notes**: assumptions, areas needing user input, jurisdiction considerations

## Guidelines

- Always ask for clarification on jurisdiction, governing law, and represented party if not provided
- Use clear, modern legal drafting style (avoid "hereinafter", "witnesseth")
- Include proper defined terms with initial capitalization
- Structure documents with logical clause numbering
- Draft complete clauses — no placeholders unless explicitly asked
- If drafting from a template, preserve the template's structure
- Consider playbook positions when choosing clause language
