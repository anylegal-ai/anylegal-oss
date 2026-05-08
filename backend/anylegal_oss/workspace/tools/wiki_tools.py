"""Wiki retrieval tools for the agentic chat.

Lets the agent search across all workspace docs at once and read compiled
wiki pages without needing N round-trips through `read_document`. Reads
the `workspace_wikis` table populated by the lexwiki-compiler sidecar.

Three tools:
    search_workspace   — BM25 search across raw doc content + wiki pages,
                         no LLM cost
    read_wiki_page     — read one compiled wiki page by slug
    list_wiki_pages    — list pages in a category (or list available indexes)
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from..session import WorkspaceSession

logger = logging.getLogger(__name__)

def _load_and_mutate_wiki(workspace_id: str, mutator):
    """Read wiki_data, run mutator(wiki_data) -> dict, persist if it returned
    a dict. Returns the persist result. Centralises the read-mutate-write
    pattern shared by all 5 edit tools.
    """
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki, update_workspace_wiki

    wiki_row = get_workspace_wiki(workspace_id)
    if not wiki_row or not wiki_row.get("wiki_data"):
        return {"error": "wiki not yet bootstrapped for this workspace — run /wiki/recompile first"}

    wiki_data = wiki_row["wiki_data"]
    result = mutator(wiki_data)
    if not isinstance(result, dict):
        return {"error": "mutator did not return a result dict"}

    ok = update_workspace_wiki(
        workspace_id,
        wiki_data,
        source_doc_count=wiki_row.get("source_doc_count") or 0,
        source_docs_hash=wiki_row.get("source_docs_hash") or "",
        cost_usd=wiki_row.get("last_compile_cost_usd"),
    )
    if not ok:
        return {"error": "failed to persist wiki update"}
    return result

ANNOTATION_TYPES = ("user", "feedback", "project", "reference")
DEFAULT_ANNOTATION_TYPE = "project"

def append_wiki_note(
    session: WorkspaceSession,
    slug: str = "",
    note: str = "",
    author: str = "ai",
    type: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Append a timestamped note. Routes by `slug`:

    - **slug provided** → append to that wiki page's `annotations` (per-doc).
      Use after a meaningful edit to that doc.
    - **slug omitted/empty** → append to `workspace_notes.annotations` (the
      workspace-level journal). Use for cross-cutting workspace insights:
      counterparty intel, user preferences, prior decisions, strategic context.

    Cheap, no LLM. Annotation shape is `{author, ts, text, type}` —
    *descriptive only* — never any severity / suggestion / finding-shaped
    evaluation fields.

    `type` taxonomy (descriptive metadata for retrieval):
      - "user"      — facts about the lawyer (role, jurisdiction, expertise).
      - "feedback"  — preferences about HOW Anylegal should behave (style, format).
      - "project"   — facts about the matter (parties, decisions, deadlines, intel). DEFAULT.
      - "reference" — pointers to external resources (Linear, Grafana, registries).

    Defaults to "project" if omitted or invalid.
    """
    if not isinstance(note, str) or not note.strip():
        return {"error": "note parameter required"}

    slug_clean = slug.strip() if isinstance(slug, str) else ""
    type_clean = (type or "").strip().lower()
    if type_clean not in ANNOTATION_TYPES:
        type_clean = DEFAULT_ANNOTATION_TYPE

    def mutator(wiki_data: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "author": author or "ai",
            "ts": datetime.now(timezone.utc).isoformat(),
            "text": note.strip(),
            "type": type_clean,
        }
        if slug_clean:
            pages = wiki_data.setdefault("pages", {})
            page = pages.get(slug_clean)
            if not page:
                return {"error": f"page not found: {slug_clean}"}
            anns = page.setdefault("annotations", [])
            anns.append(entry)
            return {
                "ok": True,
                "scope": "page",
                "slug": slug_clean,
                "type": type_clean,
                "annotation_count": len(anns),
            }

        notes = wiki_data.setdefault("workspace_notes", {"annotations": []})
        anns = notes.setdefault("annotations", [])
        anns.append(entry)
        return {
            "ok": True,
            "scope": "workspace",
            "type": type_clean,
            "annotation_count": len(anns),
        }

    return _load_and_mutate_wiki(session.session_id, mutator)

def update_wiki_page(
    session: WorkspaceSession,
    slug: str = "",
    content: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Replace a wiki page's compiled_body with a new summary.

    Use sparingly — only after you've fully restructured a doc and the
    existing compiled summary is misleading. For incremental changes, prefer
    `append_wiki_note`.
    """
    if not isinstance(slug, str) or not slug.strip():
        return {"error": "slug parameter required"}
    if not isinstance(content, str):
        return {"error": "content parameter required"}

    def mutator(wiki_data: Dict[str, Any]) -> Dict[str, Any]:
        pages = wiki_data.setdefault("pages", {})
        page = pages.get(slug)
        if not page:
            return {"error": f"page not found: {slug}"}
        page["compiled_body"] = content

        page["compiled_body_overridden"] = True
        return {"ok": True, "slug": slug}

    return _load_and_mutate_wiki(session.session_id, mutator)

def set_wiki_metadata(
    session: WorkspaceSession,
    slug: str = "",
    key: str = "",
    value: Any = None,
    **kwargs,
) -> Dict[str, Any]:
    """Patch a single frontmatter field on a wiki page.

    Allowed keys: parties, jurisdiction, effective_date, subject_areas, title.
    Use when you've established a fact about the doc that wasn't extracted
    correctly by compile.
    """
    ALLOWED = {"parties", "jurisdiction", "effective_date", "subject_areas", "title"}
    if not isinstance(slug, str) or not slug.strip():
        return {"error": "slug parameter required"}
    if key not in ALLOWED:
        return {"error": f"key must be one of {sorted(ALLOWED)}"}

    def mutator(wiki_data: Dict[str, Any]) -> Dict[str, Any]:
        pages = wiki_data.setdefault("pages", {})
        page = pages.get(slug)
        if not page:
            return {"error": f"page not found: {slug}"}
        overrides = page.setdefault("metadata_overrides", {})
        overrides[key] = value

        fm = page.setdefault("frontmatter", {})
        fm[key] = value
        return {"ok": True, "slug": slug, "key": key}

    return _load_and_mutate_wiki(session.session_id, mutator)

def delete_wiki_page(
    session: WorkspaceSession,
    slug: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Remove a wiki page. Use only when the source doc has been deleted."""
    if not isinstance(slug, str) or not slug.strip():
        return {"error": "slug parameter required"}

    def mutator(wiki_data: Dict[str, Any]) -> Dict[str, Any]:
        pages = wiki_data.setdefault("pages", {})
        if slug not in pages:
            return {"error": f"page not found: {slug}"}
        del pages[slug]
        return {"ok": True, "slug": slug, "remaining": len(pages)}

    return _load_and_mutate_wiki(session.session_id, mutator)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

def _tokenize(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]

def _score_corpus(query: str, corpus: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    """corpus items: {id, title, text, kind} — kind in {'doc', 'wiki_page'}"""
    q_terms = list(set(_tokenize(query)))
    if not q_terms:
        return []

    n_docs = len(corpus)
    if n_docs == 0:
        return []

    doc_freq: Dict[str, int] = {term: 0 for term in q_terms}
    for item in corpus:
        text_tokens = set(_tokenize(item.get("text") or ""))
        title_tokens = set(_tokenize(item.get("title") or ""))
        all_tokens = text_tokens | title_tokens
        for term in q_terms:
            if term in all_tokens:
                doc_freq[term] += 1

    import math
    idf = {
        term: math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
        for term, df in doc_freq.items()
    }

    scored: List[Dict[str, Any]] = []
    for item in corpus:
        text = item.get("text") or ""
        title = item.get("title") or ""
        tokens = _tokenize(text)
        title_tokens = _tokenize(title)
        if not tokens and not title_tokens:
            continue
        tf: Dict[str, int] = {}
        for tok in tokens:
            if tok in idf:
                tf[tok] = tf.get(tok, 0) + 1
        score = 0.0
        for term in q_terms:
            if term in tf:

                tf_v = tf[term]
                doclen = max(len(tokens), 1)
                avg_doclen = 1000.0
                norm = 1.5 * (1 - 0.75 + 0.75 * (doclen / avg_doclen))
                score += idf[term] * (tf_v * (1.5 + 1)) / (tf_v + norm)

            if term in title_tokens:
                score += idf[term] * 2.0

        if score > 0:
            scored.append({**item, "score": round(score, 4)})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

def _page_full_text(page: Dict[str, Any]) -> str:
    """Compiled body + agent annotations joined for search/agent reads.
    Backwards-compat for legacy 'content' field shape.
    """
    body = page.get("compiled_body") or page.get("content") or ""
    annotations = page.get("annotations") or []
    if annotations:
        ann_text = "\n\n".join(
            f"[note {a.get('ts','')} by {a.get('author','ai')}] {a.get('text','')}"
            for a in annotations
        )
        return body + "\n\n" + ann_text
    return body

def _build_corpus_from_wiki(wiki_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for slug, page in (wiki_data.get("pages") or {}).items():
        fm = page.get("frontmatter") or {}
        title = fm.get("title") or slug.rsplit('/', 1)[-1].replace('-', ' ')
        out.append({
            "id": slug,
            "title": str(title),
            "text": _page_full_text(page),
            "kind": "wiki_page",
            "category": page.get("category"),
        })
    return out

def _build_corpus_from_workspace(session: WorkspaceSession) -> List[Dict[str, Any]]:
    """Workspace docs as (path, title, content) triples — text only."""
    out: List[Dict[str, Any]] = []
    for path, doc in (session.documents or {}).items():

        if path.startswith(("Skills/", "Templates/", "Wiki/", ".compiled/")):
            continue

        content = getattr(doc, "content", None) or (doc.get("content") if isinstance(doc, dict) else None)
        if not isinstance(content, str) or not content.strip():
            continue
        title = path.rsplit('/', 1)[-1]
        out.append({
            "id": path,
            "title": title,
            "text": content,
            "kind": "doc",
        })
    return out

def search_workspace(
    session: WorkspaceSession,
    query: str = "",
    top_k: int = 10,
    **kwargs,
) -> Dict[str, Any]:
    """Search across the user's workspace documents AND compiled wiki pages.

    Returns the top-k matches by BM25-style relevance, no LLM cost.
    Each result shape:
        {id, title, kind: "doc" | "wiki_page", score, snippet, category?}
    """
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    if not isinstance(query, str) or not query.strip():
        return {"error": "query parameter required and must be a non-empty string", "results": []}

    try:
        top_k = max(1, min(int(top_k or 10), 50))
    except (TypeError, ValueError):
        top_k = 10

    corpus: List[Dict[str, Any]] = []

    try:
        corpus.extend(_build_corpus_from_workspace(session))
    except Exception as e:
        logger.warning(f"search_workspace: corpus(workspace) failed: {e}")

    try:
        wiki = get_workspace_wiki(session.session_id)
        if wiki and wiki.get("wiki_data"):
            corpus.extend(_build_corpus_from_wiki(wiki["wiki_data"]))
    except Exception as e:
        logger.warning(f"search_workspace: corpus(wiki) failed: {e}")

    results = _score_corpus(query, corpus, top_k)

    q_terms = [t for t in _tokenize(query) if len(t) > 2]
    for r in results:
        text = r.pop("text", "")
        snippet = ""
        if q_terms:
            lower = text.lower()
            for term in q_terms:
                idx = lower.find(term)
                if idx != -1:
                    start = max(0, idx - 80)
                    end = min(len(text), idx + 200)
                    snippet = ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")
                    break
        if not snippet and text:
            snippet = text[:240].strip() + ("…" if len(text) > 240 else "")
        r["snippet"] = snippet

    return {
        "query": query,
        "result_count": len(results),
        "results": results,
        "wiki_compiled": bool(corpus and any(r.get("kind") == "wiki_page" for r in results)),
    }

def read_wiki_page(
    session: WorkspaceSession,
    slug: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Read a single compiled wiki page by slug (e.g. 'contracts/acme-msa')."""
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    if not isinstance(slug, str) or not slug.strip():
        return {"error": "slug parameter required"}

    wiki = get_workspace_wiki(session.session_id)
    if not wiki or not wiki.get("wiki_data"):
        return {"error": "wiki not yet compiled for this workspace"}

    pages = (wiki["wiki_data"].get("pages") or {})
    page = pages.get(slug.strip())
    if not page:
        return {
            "error": f"page not found: {slug}",
            "available_count": len(pages),
            "hint": "use list_wiki_pages to browse available pages",
        }

    return {
        "slug": slug,
        "category": page.get("category"),
        "frontmatter": page.get("frontmatter") or {},
        "compiled_body": page.get("compiled_body") or page.get("content") or "",
        "annotations": page.get("annotations") or [],
    }

def list_wiki_pages(
    session: WorkspaceSession,
    category: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """List compiled wiki pages.

    `category` accepted values: 'contracts', 'statutes', 'cases', 'memos',
    'topics', or 'indexes' (returns the list of cross-cutting index names).
    Omit to return all pages grouped by category.
    """
    from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki

    wiki = get_workspace_wiki(session.session_id)
    if not wiki or not wiki.get("wiki_data"):
        return {
            "wiki_compiled": False,
            "categories": {},
            "indexes": [],
            "hint": "wiki has not been compiled for this workspace yet",
        }

    wiki_data = wiki["wiki_data"]
    pages = wiki_data.get("pages") or {}
    indexes = wiki_data.get("indexes") or {}

    if category == "indexes":
        return {
            "wiki_compiled": True,
            "indexes": sorted(indexes.keys()),
        }

    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for slug, page in pages.items():
        cat = page.get("category") or "other"
        if category and cat != category:
            continue
        fm = page.get("frontmatter") or {}
        by_cat.setdefault(cat, []).append({
            "slug": slug,
            "title": fm.get("title") or slug.rsplit('/', 1)[-1],
            "parties": fm.get("parties") or [],
            "jurisdiction": fm.get("jurisdiction"),
        })
    for cat, items in by_cat.items():
        items.sort(key=lambda x: x.get("title", "").lower())

    return {
        "wiki_compiled": True,
        "categories": by_cat,
        "page_count": sum(len(v) for v in by_cat.values()),
        "indexes": sorted(indexes.keys()),
    }

def suggest_instruction(
    session: WorkspaceSession,
    text: str = "",
    target_path: str = "anylegal.md",
    rationale: str = "",
    **kwargs,
) -> Dict[str, Any]:
    """Propose an addition to the user's anylegal.md instructions.

    DOES NOT WRITE THE FILE. Returns a payload the chat renders as a
    "Add to instructions" card. Only writes when the user clicks the
    button (which calls the existing PUT /workspace/file endpoint).

    Slash command discipline: AI proposes, user
    confirms. anylegal.md is user-authored; the AI never edits it directly.
    """
    if not isinstance(text, str) or not text.strip():
        return {"error": "text parameter required"}
    if not isinstance(rationale, str) or not rationale.strip():
        return {"error": "rationale parameter required (1-sentence justification for the user)"}

    target = (target_path or "anylegal.md").strip()
    if not target.endswith("anylegal.md"):
        return {"error": "target_path must end with 'anylegal.md'"}

    return {
        "ok": True,
        "proposed_text": text.strip(),
        "target_path": target,
        "rationale": rationale.strip(),
    }

WIKI_TOOLS = {

    "search_workspace": search_workspace,
    "read_wiki_page": read_wiki_page,
    "list_wiki_pages": list_wiki_pages,

    "append_wiki_note": append_wiki_note,
    "update_wiki_page": update_wiki_page,
    "set_wiki_metadata": set_wiki_metadata,
    "delete_wiki_page": delete_wiki_page,

    "suggest_instruction": suggest_instruction,
}
