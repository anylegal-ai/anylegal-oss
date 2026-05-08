"""CC-style memory layer assembly for the agent's per-turn system prompt.

This module assembles the memory system message:
deterministic, file-/SQL-backed, bounded layers prepended to the system
prompt every turn. No RAG. No vector search. The model never has to "know
to fetch" — relevant context is pre-loaded based on the workspace and the
currently active document.

Layers (in concat order — closer scope wins because later overrides earlier):

    1. anylegal.md cascade           [existing — handled in agentic_chat_async]
    2. AI workspace journal          (workspace_notes — new in v2 pivot)
    3. Glob-matched playbooks        (Playbook/*.md with `paths:` frontmatter)
    4. Active doc's wiki page        (compiled_body + annotations)

Each layer is wrapped with a CC-style HTML comment sentinel so log output
can be greppably attributed to a specific layer at debug time.

Hard size invariants:
    workspace_notes  ≤ 4_000 chars  (newest-first, oldest gets truncated)
    glob playbooks   ≤ 6_000 chars  (highest-precedence matches first)
    active doc page  ≤ 8_000 chars  (compiled_body first, then annotations)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from.session import WorkspaceSession

logger = logging.getLogger(__name__)

_USER_GLOBAL_MAX_CHARS = 2_000
_MANAGED_MAX_CHARS = 2_000
_WORKSPACE_NOTES_MAX_CHARS = 4_000
_PLAYBOOKS_MAX_CHARS = 6_000
_ACTIVE_DOC_PAGE_MAX_CHARS = 8_000

def build_memory_layer(
    session: WorkspaceSession,
    workspace_id: str,
    active_doc_path: Optional[str],
    user_id: Optional[int] = None,
) -> str:
    """Return a single markdown block to append to the system prompt.

    The caller (`_build_initial_messages` in agentic_chat_async.py) appends
    this block to the running `system_prompt` string right after the
    `anylegal.md` cascade and before the playbook manifest — that ordering
    keeps existing instructions first and AI memory second.

    Layer order (concat order = relevance order; later overrides earlier
    by the closer-scope-wins precedence rule):

        1. Firm-managed standards         [§ 4.2 — file at configured path]
        2. User-global preferences        [§ 4.1 — users.global_instructions]
        3. AI workspace journal           [§ 2.1 — wiki_data.workspace_notes]
        4. Glob-matched playbooks         [§ 2.5 — Playbook/*.md w/ paths:]
        5. Active doc's wiki page         [§ 2.3c]

    Empty string return = nothing to inject — caller should `if memory_block:`.
    """
    parts: List[str] = []

    managed_text = _read_managed_instructions(_MANAGED_MAX_CHARS)
    if managed_text:
        parts.append(_block(
            sentinel="AI Memory: firm-managed standards",
            heading="Firm-managed standards",
            description=(
                "Top-priority firm-wide policy rules from the IT-controlled "
                "managed instructions file. These rules cannot be overridden "
                "by user instructions; if a workspace anylegal.md conflicts, "
                "the firm policy wins."
            ),
            body=managed_text,
        ))

    if user_id:
        global_text = _read_user_global_instructions(user_id, _USER_GLOBAL_MAX_CHARS)
        if global_text:
            parts.append(_block(
                sentinel="AI Memory: user-global preferences",
                heading="Your standing preferences",
                description=(
                    "Cross-workspace preferences this user has set once and "
                    "expects to apply to every matter. Workspace-specific "
                    "anylegal.md or playbook may override per-deal."
                ),
                body=global_text,
            ))

    journal_text = _read_workspace_notes(workspace_id, _WORKSPACE_NOTES_MAX_CHARS)
    if journal_text:
        parts.append(_block(
            sentinel="AI Memory: workspace journal",
            heading="AI Memory — workspace journal",
            description=(
                "Durable facts Anylegal.ai has recorded about this matter from "
                "prior chats. Counterparty intel, user preferences, prior "
                "decisions, strategic context. Each entry tagged with `date · "
                "type · age`. **These are point-in-time observations, not live "
                "state** — verify against the current document or the user "
                "before asserting old facts as still true."
            ),
            body=journal_text,
        ))

    playbooks_text = _match_playbook_globs(session, active_doc_path, _PLAYBOOKS_MAX_CHARS)
    if playbooks_text:
        parts.append(_block(
            sentinel="AI Memory: scoped playbooks",
            heading="Playbook positions for this work",
            description=(
                "User-authored negotiation positions whose `paths:` frontmatter "
                "matches the active document. Apply these unless the user says "
                "otherwise this turn."
            ),
            body=playbooks_text,
        ))

    if active_doc_path:
        page_text = _read_active_doc_wiki(workspace_id, active_doc_path, _ACTIVE_DOC_PAGE_MAX_CHARS)
        if page_text:
            parts.append(_block(
                sentinel=f"AI Memory: active doc {active_doc_path}",
                heading=f"AI Memory of `{active_doc_path}`",
                description=(
                    "What Anylegal.ai knows about this doc from compile + chat "
                    "annotations. Use as a starting point for parties, "
                    "jurisdiction, key clauses. **Compile is point-in-time** — "
                    "if the live document conflicts with what's here, the live "
                    "document wins. Annotations carry their date and age."
                ),
                body=page_text,
            ))

    return "\n\n".join(parts)

def _block(*, sentinel: str, heading: str, description: str, body: str) -> str:
    """Format one memory layer block.

    Output shape:

        <!-- {sentinel} -->
        ## {heading}

        {description}

        {body}

    The HTML comment is invisible to the model but lets us greppably trace
    which layer produced what at debug time (follows the pattern.).
    """
    return (
        f"<!-- {sentinel} -->\n"
        f"## {heading}\n\n"
        f"{description}\n\n"
        f"{body}"
    )

def _format_age(ts: str) -> str:
    """Return a short age tag like '3d', 'yesterday', 'today', '' (today).

    Tracks memory age — age tells
    the model these are point-in-time observations, not live state.
    """
    if not ts:
        return ""
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(ts.replace("Z", ""))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta_days = (datetime.now(timezone.utc) - dt).days
    except Exception:
        return ""
    if delta_days <= 0:
        return "today"
    if delta_days == 1:
        return "yesterday"
    return f"{delta_days}d ago"

def _read_workspace_notes(workspace_id: str, max_chars: int) -> str:
    """Render the workspace journal as a bullet list, newest-first, capped.

    Each entry tagged with date · type · age. Truncation produces a tail
    warning so the model knows to consolidate when noise accumulates —
    warns when memory exceeds the rendering window.
    """
    try:
        from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki
        wiki = get_workspace_wiki(workspace_id)
    except Exception as e:
        logger.warning(f"[memory_layer] failed to read wiki for {workspace_id}: {e}")
        return ""

    if not wiki:
        return ""

    wiki_data = wiki.get("wiki_data") or {}
    notes = wiki_data.get("workspace_notes") or {}
    annotations = notes.get("annotations") or []
    if not annotations:
        return ""

    sorted_anns = sorted(
        annotations,
        key=lambda a: a.get("ts") or "",
        reverse=True,
    )
    total = len(sorted_anns)

    lines: List[str] = []
    rendered = 0
    used = 0
    for a in sorted_anns:
        text = (a.get("text") or "").strip()
        if not text:
            continue
        ts = a.get("ts") or ""
        ann_type = (a.get("type") or "project").lower()
        age = _format_age(ts)

        meta = f"{ts[:10]} · {ann_type}" + (f" · {age}" if age else "")
        line = f"- [{meta}] {text}"
        if used + len(line) + 1 > max_chars:
            if not lines:

                lines.append(line[:max_chars - 3] + "...")
                rendered = 1
            break
        lines.append(line)
        rendered += 1
        used += len(line) + 1

    omitted = total - rendered
    if omitted > 0:
        lines.append(
            f"\n> _{omitted} older journal entr{'y' if omitted == 1 else 'ies'} truncated. "
            f"Consider consolidating recurring themes into a topic page._"
        )

    return "\n".join(lines)

def _match_playbook_globs(
    session: WorkspaceSession,
    active_doc_path: Optional[str],
    max_chars: int,
) -> str:
    """Concat content of playbook files whose `paths:` matches active_doc_path."""
    matched: List[Tuple[str, str]] = []
    try:
        matched = session.match_playbooks(active_doc_path)
    except Exception as e:
        logger.warning(f"[memory_layer] match_playbooks failed: {e}")
        return ""

    if not matched:
        return ""

    parts: List[str] = []
    used = 0
    for path, body in matched:

        chunk = f"### From `{path}`\n\n{body.strip()}\n"
        if used + len(chunk) > max_chars:

            remaining = max_chars - used
            if remaining > 200:
                parts.append(chunk[:remaining - 30] + "\n[... truncated for cap...]\n")
            break
        parts.append(chunk)
        used += len(chunk)

    return "\n".join(parts)

def _read_active_doc_wiki(
    workspace_id: str,
    active_doc_path: str,
    max_chars: int,
) -> str:
    """Find the wiki page corresponding to the active doc and render it.

    Matches by either `frontmatter.source == active_doc_path` (preferred)
    or by inspecting the slug for the doc's basename. Returns the
    compiled_body + a tail of recent annotations, capped to max_chars.
    """
    try:
        from anylegal_oss.lexwiki_compiler.db import get_workspace_wiki
        wiki = get_workspace_wiki(workspace_id)
    except Exception as e:
        logger.warning(f"[memory_layer] failed to read wiki for active doc {active_doc_path}: {e}")
        return ""

    if not wiki:
        return ""

    wiki_data = wiki.get("wiki_data") or {}
    pages = wiki_data.get("pages") or {}
    if not pages:
        return ""

    page = _find_page_for_path(pages, active_doc_path)
    if not page:
        return ""

    body = (page.get("compiled_body") or page.get("content") or "").strip()
    annotations = page.get("annotations") or []

    fm = page.get("frontmatter") or {}
    fm_lines: List[str] = []
    if fm.get("title"):
        fm_lines.append(f"**Title:** {fm['title']}")
    if fm.get("parties"):
        parties = fm["parties"]
        if isinstance(parties, list):
            parties = ", ".join(str(p) for p in parties)
        fm_lines.append(f"**Parties:** {parties}")
    if fm.get("jurisdiction"):
        fm_lines.append(f"**Jurisdiction:** {fm['jurisdiction']}")
    if fm.get("effective_date"):
        fm_lines.append(f"**Effective:** {fm['effective_date']}")

    rendered = ""
    if fm_lines:
        rendered += "\n".join(fm_lines) + "\n\n"
    if body:
        rendered += body

    if annotations:
        sorted_anns = sorted(
            annotations,
            key=lambda a: a.get("ts") or "",
            reverse=True,
        )
        ann_lines: List[str] = ["\n\n### Notes from chat"]
        for a in sorted_anns:
            text = (a.get("text") or "").strip()
            if not text:
                continue
            ts = a.get("ts") or ""
            ann_type = (a.get("type") or "project").lower()
            age = _format_age(ts)
            meta = f"{ts[:10]} · {ann_type}" + (f" · {age}" if age else "")
            ann_lines.append(f"- [{meta}] {text}")
        rendered += "\n".join(ann_lines)

    if len(rendered) > max_chars:
        rendered = rendered[:max_chars - 30] + "\n[... truncated for cap...]"

    return rendered

def _find_page_for_path(
    pages: Dict[str, Dict[str, Any]],
    active_doc_path: str,
) -> Optional[Dict[str, Any]]:
    """Find the wiki page that corresponds to active_doc_path.

    The compiler materializes workspace docs into scratch as `<safe>.md` and
    writes that scratch filename to the page's `source_raw` frontmatter. We
    invert that mapping here: compute the same safe filename from the active
    doc's path and look it up in `source_raw`.

    Falls back to a slug-substring heuristic if no exact match is found
    (e.g. for source_raw fields the LLM didn't preserve verbatim).
    """
    if not active_doc_path:
        return None

    import re
    basename = active_doc_path.rsplit('/', 1)[-1]
    stem = basename.rsplit('.', 1)[0] if '.' in basename else basename
    flat = active_doc_path.replace('/', '__').replace('\\', '__')
    flat_stem = flat.rsplit('.', 1)[0] if '.' in flat.rsplit('/', 1)[-1] else flat
    safe = re.sub(r'[^a-zA-Z0-9_\-]+', '_', flat_stem).strip('_').lower()
    safe = (safe or "doc")[:100] + ".md"

    for page in pages.values():
        fm = page.get("frontmatter") or {}
        sr = fm.get("source_raw")
        if isinstance(sr, str) and sr.lower() == safe:
            return page

        b_safe = re.sub(r'[^a-zA-Z0-9_\-]+', '_', stem).strip('_').lower() + '.md'
        if isinstance(sr, str) and sr.lower() == b_safe:
            return page

    base_lower = stem.lower()
    base_clean = re.sub(r'[^a-z0-9]+', '', base_lower)
    if not base_clean:
        return None
    for slug, page in pages.items():
        slug_tail = slug.rsplit('/', 1)[-1].lower()
        slug_clean = re.sub(r'[^a-z0-9]+', '', slug_tail)
        if base_clean in slug_clean or slug_clean in base_clean:
            return page
    return None

def _read_user_global_instructions(user_id: int, max_chars: int) -> str:
    """Read the user's `users.global_instructions` column. § 4.1."""
    try:
        from anylegal_oss.db.database import get_user_global_instructions
        text = get_user_global_instructions(user_id)
    except Exception as e:
        logger.warning(f"[memory_layer] failed to read user-global for {user_id}: {e}")
        return ""
    if not text:
        return ""
    return text if len(text) <= max_chars else text[:max_chars - 30] + "\n[... truncated...]"

_MANAGED_CACHE: Dict[str, Any] = {"path": None, "mtime": 0.0, "content": ""}

def _read_managed_instructions(max_chars: int) -> str:
    """Read the firm-managed instructions file. § 4.2.

    Path is configurable via env `ANYLEGAL_MANAGED_INSTRUCTIONS_PATH` and
    defaults to a neutral path under the configured workspace data dir.
    No firm entity model exists yet — when one is shipped, we drop a
    file at the configured path and the layer picks it up automatically.
    """
    import os
    from pathlib import Path
    path = os.environ.get(
        "ANYLEGAL_MANAGED_INSTRUCTIONS_PATH",
        "./data/managed/anylegal.md",
    )
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ""
        mtime = p.stat().st_mtime
        if (
            _MANAGED_CACHE.get("path") == path
            and _MANAGED_CACHE.get("mtime") == mtime
        ):
            cached = _MANAGED_CACHE.get("content") or ""
            return cached if len(cached) <= max_chars else cached[:max_chars - 30] + "\n[... truncated...]"
        text = p.read_text(encoding="utf-8").strip()
        _MANAGED_CACHE["path"] = path
        _MANAGED_CACHE["mtime"] = mtime
        _MANAGED_CACHE["content"] = text
        return text if len(text) <= max_chars else text[:max_chars - 30] + "\n[... truncated...]"
    except Exception as e:
        logger.warning(f"[memory_layer] failed to read managed instructions {path}: {e}")
        return ""
