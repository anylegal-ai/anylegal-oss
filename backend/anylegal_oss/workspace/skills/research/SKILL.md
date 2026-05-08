---
name: research
emoji: "\U0001F310"
description: Research a legal topic with web search and inline citations. Use when the user needs legal information, market standards, regulatory guidance, or case law references.
requires:
  tools: [web_search, web_fetch, run_code, read_document, list_documents, create_document]
---

# Legal Research

## When to Use

Use this skill when:
- The user asks a legal question or wants to know about a law/regulation
- The user says /research
- The user asks about market standards, typical terms, or industry norms
- The user needs jurisdiction-specific legal information
- The user asks for regulatory guidance or compliance information

## Process

1. **Identify jurisdiction** — infer from the question, document context, or session context. If ambiguous, ask the user.
2. **Match language** — search in the same language the user is writing in. If the user writes in Russian, use Russian-language search queries first (e.g., "ограничение ответственности SaaS договор"). Add English queries only as supplement if Russian results are insufficient.
3. **Search authoritative sources first** — use `web_search` with the jurisdiction set, targeting official government and institutional domains for statutory text, regulations, and case law. Frame queries with specific section/article numbers when known.
4. **Read full pages with `web_fetch`** — once you have URLs to authoritative sources, fetch them to get complete article/section text. Don't rely on search snippets for citations.
5. **Cross-reference** — for any cited statute or case, run a follow-up search to verify the citation is correct, current, and not superseded.
6. **Supplement with secondary sources** — use `web_search` for legal commentary, market standards, regulatory guidance, and practitioner analysis. Tag these as "commentary" rather than authority.
7. **Synthesize** the findings into a clear answer with inline citations.
8. **Cite every factual claim** using `[[N]](URL)` format. Start numbering from **[1]** in every new response or document — never continue numbering from earlier messages.

## Output Format

Structure research responses as:

- **Answer**: Direct, practical answer to the question with inline citations
- **Jurisdiction Context**: Which jurisdiction this applies to and any cross-jurisdiction notes
- **Key Points**: Bullet points of the most important findings, each cited
- **Practical Recommendations**: What the user should do based on the research
- **Sources**: Numbered list of all sources cited

### Citation Format (MANDATORY)

Every factual claim MUST have an inline citation:

```
The Companies Act 2006 (UK) requires directors to act in accordance with the company's constitution [[1]](https://url-to-source).
```

End every research response with:

```
## Sources
1. [Title of source](URL)
2. [Title of source](URL)
```

## Creating a Research Document

When the user asks to create a document (memo, note, report) from research:

1. **Write in the user's language** — if the conversation is in Russian, the document must be in Russian. Match the language of the request, not the language of sources.
2. **Use `run_code`** (default Python) with python-docx to create the document with proper formatting (headings, bold defined terms, tables). Write the complete document in a single script. For simple markdown notes, `create_document` is acceptable.
3. **After creation, ALWAYS `read_document`** to verify: correct language, citation numbering starts at [1], all sections present, formatting intact. Fix any issues before reporting success.
4. **Citation numbering starts at [1]** in every new document, regardless of what was cited in earlier chat messages.

## Guidelines

- Prefer official government and institutional sources over secondary commentary
- If you cannot find a source for a claim, say "I could not verify this — please check independently"
- Do NOT invent URLs, case names, statute numbers, or regulatory references
- If web search returns no relevant results, say so — do not fabricate citations
- Verify statutes are still in force before citing them — laws change, search results may be outdated
- Consider multiple jurisdictions if the question is cross-border
- Note when laws have been recently amended or are under review
- Distinguish between binding law and non-binding guidance
- **Language**: Search queries, document content, and response text should all match the user's language
