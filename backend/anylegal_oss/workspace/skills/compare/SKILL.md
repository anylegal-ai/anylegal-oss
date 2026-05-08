---
name: compare
emoji: "\U0001F504"
description: Compare two document versions and produce analysis or a Word redline. Use when the user has two versions of a document and wants to understand what changed.
requires:
  tools: [read_document, compare, run_code, list_documents]
---

# Document Comparison

## When to Use

Use this skill when:
- The user uploads two versions of the same document
- The user says /compare
- The user asks "what changed", "what's different", or "show me the differences"
- The user asks for a redline or tracked-changes document
- The user received a counterparty markup and wants to understand the changes

## Process

1. **Identify the two documents** — ask the user which is the original and which is the revised version if not clear
2. **Read both documents** via `read_document`
3. **Run `compare`** with both document paths or texts — this returns a structured diff, similarity percentage, and visual output
4. **Analyze the differences:**
   - What was added, removed, or modified?
   - Which changes are substantive vs. editorial?
   - Are any changes risky or favorable?
   - Do changes align with playbook positions (if available in context)?
5. **Present findings** with a summary of key changes
6. **If user wants a Word redline** — call `run_code` (default Python) to generate a DOCX with tracked changes. Open the original with python-docx, compute a diff against the revised text, and insert `w:ins`/`w:del` tracked-change markup via lxml. See `/docx-editing` skill for OOXML tracked change patterns. Verify the output with structural checks.

## Output Format

- **Summary**: Overall similarity %, number of changes, nature of changes (substantive vs. editorial)
- **Key Changes**: List of the most significant changes with assessment:
  - What changed
  - Why it matters (risk/benefit)
  - Recommendation (accept / reject / negotiate)
- **Full Change List**: All detected changes in order
- **Action Items**: What to do next (accept, push back, request clarification)

## Guidelines

- Always present the original vs. revised framing clearly
- Distinguish substantive changes (liability caps, notice periods, governing law) from editorial changes (formatting, numbering, defined terms)
- Prioritize substantive changes in the summary
- If playbook is available, flag changes that deviate from firm positions
- When producing a DOCX redline, confirm which direction the user wants (their changes tracked, or counterparty changes tracked)
