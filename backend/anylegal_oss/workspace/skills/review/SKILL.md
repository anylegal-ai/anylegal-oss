---
name: review
emoji: "\U0001F50D"
description: Review a document against playbook positions. Analyze clauses for risks, flag issues, suggest specific changes, and apply edits. Subsumes redlining — review + fix is one workflow.
requires:
  tools: [read_document, edit_document, revert_edit, get_revision_stats, compare, list_documents, web_search, web_fetch]
---

# Contract Review

## When to Use

Use this skill when:
- The user asks to review a contract or document
- The user wants a risk assessment or issue-spotting pass
- The user says /review
- The user asks to "check", "flag", "audit", or "assess" a document
- The user asks to review and then apply changes (review + redline is one flow)

## Process

1. **Identify which document to review** — Check the "Active document" in your context. If the active document is a contract/agreement in the workspace documents list, review it. If the active document is an instructions file, playbook, template, or other non-contract file (or if no document is active), ask the user which document they want reviewed. List the available workspace documents and let them pick.
2. **Read the document** via `read_document` — always read the full document first
3. **Read the relevant playbook(s)** — check the "Available Playbooks" manifest in your context, then call `read_document("Playbook/<filename>")` to load the one(s) relevant to this contract type, jurisdiction, or client
4. **Research jurisdiction-specific requirements** — identify the governing law from the contract, then:
   - Use `web_search` with the jurisdiction set to find relevant statutes and regulations for the contract type
   - Use `web_fetch` to retrieve full statutory text from authoritative sources (government domains, official gazettes)
   - Cross-reference: for any cited statute, run a follow-up search to verify it is current and not superseded
   - Use `web_search` for case law, regulatory guidance, and market standards (recent enforcement trends, standard market positions for the industry)
5. **Analyze each key clause:**
   - Identify clause type (indemnification, limitation of liability, termination, etc.)
   - Assess position: favorable, balanced, or unfavorable for the represented party
   - Determine risk level: low, medium, high, or critical
   - Check alignment with playbook positions
   - Flag any clauses that conflict with mandatory statutory requirements — cite the exact source URL retrieved via `web_fetch`
   - Use `web_search` to check market standards if the clause deviates from typical positions
   - Consider market standards and jurisdiction-specific requirements
6. **Present findings** in structured format with specific recommendations
7. **If user asks to apply changes ("redline", "implement", "apply", "do it"):**
   - Invoke `Skill(skill="docx-editing")` for the full edit-pattern library, then call `edit_document` for each change. Edit the document in place — do not clone to a `_v2` copy.
   - Copy the EXACT text span from the document — do not paraphrase or reconstruct from memory. Use the shortest unique snippet for `old_text`.
   - `edit_document` emits `<w:ins>` / `<w:del>` tracked-change markup automatically. Author defaults to `"Anylegal.ai"` — pass an explicit author only if the user supplies a different name.
   - Do NOT just describe changes — actually call `edit_document` for each one.
   - Do NOT use `run_code` for text edits.

## Output Format

Provide analysis as:

- **Executive Summary**: Overall risk level, key concerns, recommendation (proceed / negotiate / reject)
- **Clause-by-Clause Analysis**: For each significant clause:
  - Clause reference and type
  - Current position and risk level
  - Playbook alignment (if playbook available)
  - Specific recommendation with suggested replacement language
- **Statutory Compliance**: Any mandatory requirements from the governing jurisdiction that the contract must meet, with citations to authoritative sources
- **Priority Actions**: Top 3-5 items to negotiate first

### Risk Levels

- **low**: Standard language, well-balanced, no significant exposure
- **medium**: Some deviation from market standard, limited exposure
- **high**: Significant exposure, one-sided provisions, should be negotiated
- **critical**: Unacceptable risk, deal-breaker if not changed

## Guidelines

- Always consider the full document context, not just isolated clauses
- Check for related clauses that may mitigate or compound risks
- Reference specific clause numbers
- Consider the contract type and industry context
- When playbook positions exist, clearly indicate alignment or deviation
- Be specific in recommendations — draft actual replacement language
- If the user asks to "implement" or "apply" changes, invoke `Skill(skill="docx-editing")` and call `edit_document` for each change. Edit in place. Copy EXACT text from the document — never from memory.
- **Proactively research** — don't just rely on your training data for legal requirements. Use `web_search` and `web_fetch` against authoritative jurisdiction-specific sources to verify statutory requirements. Cite source URLs when flagging compliance issues.
- When flagging a statutory requirement, retrieve and quote the exact provision text from an authoritative source so you can cite it precisely.
