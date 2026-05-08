"""Per-workspace compile cycle.

Reads encrypted workspace blob from sqlite -> writes decrypted source docs
to a scratch dir -> runs LexWiki compile + lint -> stuffs the result back
into workspace_wikis (encrypted). Wipes scratch on the way out.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import Config
from . import lexwiki_runner

logger = logging.getLogger(__name__)

EXCLUDED_PREFIXES = (
    "Skills/",
    "Templates/",
    "Playbook/",
    "Wiki/",                                        
    ".compiled/",
    "anylegal.md",                                              
)

TEXT_FORMATS = {"txt", "md", "markdown"}

def _is_compilable(path: str, doc: Dict[str, Any], has_blob: bool = False) -> bool:
    """A doc is compilable if it has either pre-extracted text content OR a
    docx_blob we can run through lexwiki's extractor. Skills/Templates/etc.
    are always excluded.
    """
    if any(path.startswith(prefix) or path == prefix.rstrip('/') for prefix in EXCLUDED_PREFIXES):
        return False
    content = doc.get("content")
    if isinstance(content, str) and content.strip():
        return True
    if has_blob:
        return True
    return False

def _safe_filename(path: str) -> str:
    """Convert a workspace path like 'Clients/Acme/MSA.docx' into a flat
    filename like 'clients__acme__msa.md'. Lowercased, slashes -> double
    underscore, non-alnum dropped. We always emit .md because all workspace
    content is already extracted text.
    """
    stem = path.rsplit('.', 1)[0] if '.' in path.rsplit('/', 1)[-1] else path
    flat = stem.replace('/', '__').replace('\\', '__')
    safe = re.sub(r'[^a-zA-Z0-9_\-]+', '_', flat).strip('_').lower()
    return (safe or "doc")[:100] + ".md"

def _doc_signature(
    path: str,
    doc: Dict[str, Any],
    blob: Optional[bytes] = None,
) -> str:
    """Per-doc hash for the per-doc skip path. Mirrors the
    (path, modified_at, content_len|blob_len) tuple used by
    _compute_source_hash so 'changed' means the same thing at both levels.
    """
    modified_at = str(doc.get("modified_at") or doc.get("created_at") or "")
    content = doc.get("content") or ""
    size = len(content) if content else len(blob or b"")
    return hashlib.sha256(repr((path, modified_at, size)).encode('utf-8')).hexdigest()

def _compute_source_hash(
    documents: Dict[str, Any],
    docx_blobs: Optional[Dict[str, bytes]] = None,
) -> str:
    """Hash of compilable docs' (path, modified_at, content_len|blob_len) tuples.
    Used to skip recompile when nothing material changed at the workspace level.
    """
    docx_blobs = docx_blobs or {}
    tuples: List[Tuple[str, str, int]] = []
    for path, doc in sorted(documents.items()):
        if not _is_compilable(path, doc, has_blob=bool(docx_blobs.get(path))):
            continue
        modified_at = str(doc.get("modified_at") or doc.get("created_at") or "")
        content = doc.get("content") or ""
        size = len(content) if content else len(docx_blobs.get(path) or b"")
        tuples.append((path, modified_at, size))
    h = hashlib.sha256()
    for t in tuples:
        h.update(repr(t).encode('utf-8'))
    return h.hexdigest()

def _serialize_page_to_markdown(page: Dict[str, Any]) -> str:
    """Round-trip a wiki_data page back to the on-disk markdown lexwiki wrote.

    Used to rehydrate `wiki_dir/<slug>.md` for unchanged docs so that the
    index rebuild + backlinks passes see the full corpus, not just docs we
    actually recompiled this turn. Annotations are NOT serialized — they
    live only in the encrypted DB; lexwiki has no concept of them.
    """
    import yaml  # noqa: WPS433
    fm = page.get("frontmatter") or {}
    body = page.get("compiled_body") or ""
    try:
        fm_yaml = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False).strip()
    except Exception:

        fm_yaml = "title: \"" + str(fm.get("title", "")).replace('"', "'") + "\""
    return f"---\n{fm_yaml}\n---\n\n{body}"

def _rehydrate_unchanged_pages(
    skip_set: Dict[str, Dict[str, Any]],
    raw_dir: Path,
    wiki_dir: Path,
) -> int:
    """For each (source_path -> {stem, slug, page}) in skip_set:

      1. Write the prior compiled page back to wiki_dir/<slug>.md so the
         index rebuild + backlinks passes see the full corpus.
      2. Write a fresh marker at raw_dir/.compiled/<stem>.marker so lexwiki's
         `_is_compiled(raw_path)` returns True and skips the LLM call.

    Materialize_raw_docs has already written the raw .md to disk; we touch
    the marker AFTER, so its mtime is naturally >= the raw file's mtime
    (which is what lexwiki's skip predicate compares).

    Returns the count of pages successfully rehydrated.
    """
    markers_dir = raw_dir / ".compiled"
    markers_dir.mkdir(parents=True, exist_ok=True)
    rehydrated = 0
    for source_path, info in skip_set.items():
        slug = info.get("slug")
        stem = info.get("stem")
        prior_page = info.get("page")
        if not (slug and stem and prior_page):
            continue
        try:
            page_path = wiki_dir / f"{slug}.md"
            page_path.parent.mkdir(parents=True, exist_ok=True)
            page_path.write_text(
                _serialize_page_to_markdown(prior_page), encoding='utf-8'
            )
            (markers_dir / f"{stem}.marker").write_text(
                datetime.now(timezone.utc).isoformat(),
                encoding='utf-8',
            )
            rehydrated += 1
        except Exception as e:
            logger.warning(
                f"Failed to rehydrate page for {source_path} "
                f"(slug={slug}, stem={stem}): {e}"
            )
    return rehydrated

def _materialize_raw_docs(
    documents: Dict[str, Any],
    docx_blobs: Dict[str, bytes],
    raw_dir: Path,
    source_dir: Path,
    *,
    max_docs: int,
    max_chars: int,
) -> Tuple[int, Dict[str, str]]:
    """Get every compilable workspace doc into `raw_dir` as a `.md` file.

    Two paths:
      - Doc has pre-extracted text content -> write .md directly with YAML
        frontmatter (skips lexwiki's extractor — fast path).
      - Doc has empty content but a docx_blob (typical for uploaded DOCX
        whose text is extracted lazily on read) -> dump the blob to
        `source_dir` as .docx and run `lexwiki.extract.router.ingest_file`
        to convert to .md in raw_dir.

    Returns:
        (written_count, raw_stem_to_source) — the second value maps each
        raw filename's stem (without `.md`) back to its workspace path, so
        the per-doc compiler can attribute compiled pages to source paths.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    raw_stem_to_source: Dict[str, str] = {}
    for path, doc in sorted(documents.items()):
        if written >= max_docs:
            logger.info(f"Hit max_docs={max_docs}, skipping remainder")
            break
        blob = docx_blobs.get(path)
        if not _is_compilable(path, doc, has_blob=bool(blob)):
            continue

        content = doc.get("content") or ""
        if isinstance(content, str) and content.strip():

            if len(content) > max_chars:
                content = content[:max_chars] + "\n\n[... truncated for compilation budget ...]\n"
            fmt = doc.get("format") or "md"
            modified_at = doc.get("modified_at") or doc.get("created_at") or ""
            title = path.rsplit('/', 1)[-1].rsplit('.', 1)[0]
            frontmatter = (
                "---\n"
                f"source: {path}\n"
                f"title: {title}\n"
                f"format: {fmt}\n"
                f"modified_at: {modified_at}\n"
                f"word_count: {len(content.split())}\n"
                "---\n"
            )
            safe_name = _safe_filename(path)
            target = raw_dir / safe_name
            try:
                target.write_text(frontmatter + content, encoding='utf-8')
                written += 1
                raw_stem_to_source[Path(safe_name).stem] = path
            except Exception as e:
                logger.warning(f"Failed to materialize {path} -> {target}: {e}")
            continue

        if not blob:
            continue
        try:
            from lexwiki.extract.router import ingest_file  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(f"lexwiki not available — skipping blob extraction for {path}")
            continue
        try:
            safe_stem = Path(_safe_filename(path)).stem
            tmp_docx = source_dir / (safe_stem + ".docx")
            tmp_docx.write_bytes(blob)
            ingest_file(tmp_docx, raw_dir)
            written += 1

            raw_stem_to_source[safe_stem] = path
        except Exception as e:
            logger.warning(f"Failed to extract docx blob for {path}: {e}")
            continue

    return written, raw_stem_to_source

def compile_workspace(workspace_id: str, cfg: Config) -> Dict[str, Any]:
    """Compile one workspace end-to-end.

    Returns a small status dict suitable for logging:
        {ok, status, source_doc_count, skipped_reason?, error?}

    Exceptions are caught and translated into status='error' with the
    workspace_wikis row updated accordingly.
    """
    from .db import (
        get_workspace_for_compile,
        get_workspace_wiki,
        update_workspace_wiki,
        update_workspace_wiki_status,
    )

    t0 = time.time()
    workspace = get_workspace_for_compile(workspace_id)
    if not workspace:
        return {"ok": False, "error": "workspace not found"}

    compile_model = cfg.model

    documents = workspace.get("documents") or {}
    docx_blobs = workspace.get("docx_blobs") or {}
    compilable_count = sum(
        1
        for p, d in documents.items()
        if _is_compilable(p, d, has_blob=bool(docx_blobs.get(p)))
    )
    if compilable_count == 0:

        update_workspace_wiki(
            workspace_id,
            {"pages": {}, "indexes": {}, "workspace_notes": {"annotations": []}},
            source_doc_count=0,
            source_docs_hash="empty",
            cost_usd=0.0,
        )
        return {"ok": True, "status": "ready", "source_doc_count": 0, "skipped_reason": "no compilable docs"}

    current_hash = _compute_source_hash(documents, docx_blobs)
    existing = get_workspace_wiki(workspace_id)
    if existing and existing.get("source_docs_hash") == current_hash and existing.get("compile_status") == "ready":
        return {"ok": True, "status": "ready", "source_doc_count": compilable_count, "skipped_reason": "unchanged"}

    update_workspace_wiki_status(workspace_id, "compiling", error=None)

    scratch_root = cfg.scratch_dir / workspace_id
    if scratch_root.exists():
        shutil.rmtree(scratch_root, ignore_errors=True)
    raw_dir = scratch_root / "raw"
    wiki_dir = scratch_root / "wiki"
    source_dir = scratch_root / "source"
    raw_dir.mkdir(parents=True, exist_ok=True)
    wiki_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)

    try:
        written, raw_stem_to_source = _materialize_raw_docs(
            documents,
            docx_blobs,
            raw_dir,
            source_dir,
            max_docs=cfg.max_docs_per_workspace,
            max_chars=cfg.max_doc_chars,
        )
        if written == 0:
            update_workspace_wiki(
                workspace_id,
                {"pages": {}, "indexes": {}, "workspace_notes": {"annotations": []}},
                source_doc_count=0,
                source_docs_hash=current_hash,
                cost_usd=0.0,
            )
            return {"ok": True, "status": "ready", "source_doc_count": 0, "skipped_reason": "materialize wrote 0"}

        prior_data: Dict[str, Any] = {}
        prior_pages: Dict[str, Any] = {}
        prior_source_index: Dict[str, Any] = {}
        if existing and isinstance(existing, dict):
            prior_data = existing.get("wiki_data") or {}
            prior_pages = prior_data.get("pages") or {}
            prior_source_index = prior_data.get("source_index") or {}

        skip_set: Dict[str, Dict[str, Any]] = {}

        materialized_paths = set(raw_stem_to_source.values())
        for source_path in materialized_paths:
            doc = documents.get(source_path)
            if not doc:
                continue
            prior_entry = prior_source_index.get(source_path)
            if not prior_entry:
                continue
            current_doc_hash = _doc_signature(
                source_path, doc, docx_blobs.get(source_path)
            )
            if prior_entry.get("source_hash") != current_doc_hash:
                continue
            slug = prior_entry.get("slug")
            stem = prior_entry.get("stem")
            if not slug or not stem:
                continue
            prior_page = prior_pages.get(slug)
            if not prior_page:
                continue
            skip_set[source_path] = {
                "stem": stem,
                "slug": slug,
                "source_hash": current_doc_hash,
                "page": prior_page,
            }

        if skip_set:
            rehydrated = _rehydrate_unchanged_pages(skip_set, raw_dir, wiki_dir)
            logger.info(
                f"[{workspace_id}] per-doc skip: rehydrated {rehydrated}/"
                f"{len(skip_set)} unchanged pages, will recompile "
                f"{written - rehydrated} doc(s)"
            )

        compile_result = lexwiki_runner.compile_vault_per_doc(
            scratch_root,
            model=compile_model,
            base_url=cfg.base_url,
            raw_stem_to_source=raw_stem_to_source,
        )
        stats = compile_result["stats"]
        compiled_source_to_slug = compile_result["source_to_slug"]
        logger.info(
            f"[{workspace_id}] compile stats (model={compile_model}, "
            f"skipped={len(skip_set)}, compiled={len(compiled_source_to_slug)}): {stats}"
        )

        wiki_data = lexwiki_runner.read_compiled_vault(scratch_root)

        for slug, fresh_page in wiki_data["pages"].items():
            prior = prior_pages.get(slug)
            if not prior:
                continue
            fresh_page["annotations"] = prior.get("annotations") or []
            overrides = prior.get("metadata_overrides") or {}
            if overrides:
                fresh_page["metadata_overrides"] = overrides
        prior_workspace_notes = prior_data.get("workspace_notes")
        if prior_workspace_notes:
            wiki_data["workspace_notes"] = prior_workspace_notes

        fresh_source_index: Dict[str, Any] = {}

        for source_path, info in skip_set.items():
            fresh_source_index[source_path] = {
                "stem": info["stem"],
                "slug": info["slug"],
                "source_hash": info["source_hash"],
            }

        for source_path, slug in compiled_source_to_slug.items():
            doc = documents.get(source_path)
            if not doc:
                continue
            stem = next(
                (s for s, p in raw_stem_to_source.items() if p == source_path),
                None,
            )
            if not stem:
                continue
            fresh_source_index[source_path] = {
                "stem": stem,
                "slug": slug,
                "source_hash": _doc_signature(
                    source_path, doc, docx_blobs.get(source_path)
                ),
            }
        wiki_data["source_index"] = fresh_source_index

        ok = update_workspace_wiki(
            workspace_id,
            wiki_data,
            source_doc_count=written,
            source_docs_hash=current_hash,
            cost_usd=None,
        )
        if not ok:
            raise RuntimeError("update_workspace_wiki returned False")

        elapsed = time.time() - t0
        return {
            "ok": True,
            "status": "ready",
            "source_doc_count": written,
            "page_count": len(wiki_data.get("pages") or {}),
            "skipped_count": len(skip_set),
            "compiled_count": len(compiled_source_to_slug),
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as e:
        logger.exception(f"[{workspace_id}] compile failed")
        update_workspace_wiki_status(workspace_id, "error", error=str(e)[:500])
        return {"ok": False, "status": "error", "error": str(e)}

    finally:

        shutil.rmtree(scratch_root, ignore_errors=True)
