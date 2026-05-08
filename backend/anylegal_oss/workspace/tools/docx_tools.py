"""
DOCX Tools for Workspace

Tool implementations for DOCX tracked-change operations:
- get_revision_stats — count/list tracked changes in a document.
- revert_edit — undo specific tracked changes by revision ID.
- accept_all_changes / reject_all_changes — finalize via LibreOffice.
"""

import logging
from typing import Any, Dict, Optional

from ..session import WorkspaceSession

logger = logging.getLogger(__name__)

def get_revision_stats(
    session: WorkspaceSession,
    path: str,
    with_snippets: bool = False,
    **kwargs
) -> Dict[str, Any]:
    """
    Get statistics about tracked changes in a document.

    Args:
        session: Workspace session
        path: Path to document to analyze
        with_snippets: When True, returns per-revision detail with
            text snippets and context (use to pick IDs for selective
            accept_changes / reject_changes). Default False keeps the
            response cheap.
    """
    from ..docx_revision_service import DocxRevisionService

    try:
        doc = session.get_document(path)
        if not doc:
            return {
                "success": False,
                "error": f"Document not found: {path}"
            }

        if not doc.docx_blob:
            return {
                "success": True,
                "path": path,
                "has_revisions": False,
                "message": "Document has no DOCX - no track changes available"
            }

        stats = DocxRevisionService.get_revision_stats(doc.docx_blob, with_snippets=with_snippets)

        return {
            "success": True,
            "path": path,
            **stats
        }

    except Exception as e:
        logger.error(f"get_revision_stats failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }

def accept_changes(
    session: WorkspaceSession,
    path: str,
    revision_ids: list,
    **kwargs
) -> Dict[str, Any]:
    """
    Accept specific tracked changes by revision ID.

    For each ID:
      - <w:ins> → unwrap (insertion becomes permanent)
      - <w:del> → drop entirely (deleted text stays gone)

    Auto-clones the pristine original to ``_v2`` on first call (mirrors
    edit_document / accept_all_changes safety net) so the source-of-truth
    isn't mutated.

    Returns ``{success, path, doc_type: "docx", accepted_ids, not_found_ids,
    cloned_from?}``. The ``doc_type: "docx"`` field triggers the frontend
    preview-refresh contract — see useAgenticChat.ts handler.
    """
    from ..docx_xml_service import accept_specific_changes, validate_document_xml
    from .document_tools import resolve_or_clone_to_v2

    try:
        if not revision_ids:
            return {"success": False, "error": "revision_ids must be a non-empty list"}

        resolved_path, cloned_from = resolve_or_clone_to_v2(session, path)
        path = resolved_path

        doc = session.get_document(path)
        if not doc:
            return {"success": False, "error": f"Document not found: {path}"}
        if not doc.docx_blob:
            return {"success": False, "error": f"Document {path} has no DOCX - cannot accept changes"}

        xml_content = doc.document_xml
        if xml_content is None:
            return {"success": False, "error": "Failed to extract XML from DOCX blob"}

        new_xml, info = accept_specific_changes(xml_content, revision_ids)
        if info.get("error"):
            return {"success": False, "error": info["error"]}

        errors = validate_document_xml(new_xml)
        parse_errors = [e for e in errors if e.startswith("XML parse error")]
        if parse_errors:
            return {
                "success": False,
                "error": f"XML invalid after accept: {parse_errors[0]}",
                "validation_errors": errors,
            }

        doc.update_document_xml(new_xml)

        result: Dict[str, Any] = {
            "success": True,
            "path": path,
            "doc_type": "docx",
            "accepted_ids": info.get("accepted_ids", []),
            "not_found_ids": info.get("not_found_ids", []),
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
        return result

    except Exception as e:
        logger.error(f"accept_changes failed: {e}")
        return {"success": False, "error": str(e)}

def reject_changes(
    session: WorkspaceSession,
    path: str,
    revision_ids: list,
    **kwargs
) -> Dict[str, Any]:
    """
    Reject specific tracked changes by revision ID.

    For each ID:
      - <w:ins> → drop entirely (inserted text disappears)
      - <w:del> → unwrap, restore <w:delText> as <w:t> (deleted text returns)

    Same auto-clone safety net as accept_changes. Returns
    ``{success, path, doc_type, rejected_ids, not_found_ids, cloned_from?}``.

    Implementation reuses ``revert_tracked_changes`` since reject has the
    same XML semantics — same operation, different framing.
    """
    from ..docx_xml_service import revert_tracked_changes, validate_document_xml
    from .document_tools import resolve_or_clone_to_v2

    try:
        if not revision_ids:
            return {"success": False, "error": "revision_ids must be a non-empty list"}

        resolved_path, cloned_from = resolve_or_clone_to_v2(session, path)
        path = resolved_path

        doc = session.get_document(path)
        if not doc:
            return {"success": False, "error": f"Document not found: {path}"}
        if not doc.docx_blob:
            return {"success": False, "error": f"Document {path} has no DOCX - cannot reject changes"}

        xml_content = doc.document_xml
        if xml_content is None:
            return {"success": False, "error": "Failed to extract XML from DOCX blob"}

        new_xml, info = revert_tracked_changes(xml_content, revision_ids)
        if info.get("error"):
            return {"success": False, "error": info["error"]}

        errors = validate_document_xml(new_xml)
        parse_errors = [e for e in errors if e.startswith("XML parse error")]
        if parse_errors:
            return {
                "success": False,
                "error": f"XML invalid after reject: {parse_errors[0]}",
                "validation_errors": errors,
            }

        doc.update_document_xml(new_xml)

        result: Dict[str, Any] = {
            "success": True,
            "path": path,
            "doc_type": "docx",
            "rejected_ids": info.get("reverted_ids", []),
            "not_found_ids": info.get("not_found_ids", []),
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
        return result

    except Exception as e:
        logger.error(f"reject_changes failed: {e}")
        return {"success": False, "error": str(e)}

def revert_edit(
    session: WorkspaceSession,
    path: str,
    revision_ids: list,
    **kwargs
) -> Dict[str, Any]:
    """
    Undo specific tracked changes by revision ID.

    Surgically removes the ``<w:del>``/``<w:ins>`` pairs for the given IDs,
    restoring the original text.  Other tracked changes are untouched.

    Passes through the same auto-clone-to-v2 safety net as
    ``edit_document``: if ``path`` is the pristine original and a ``_v{N}``
    working copy already exists, the revert routes there; if no working
    copy exists yet and the original has tracked changes, it clones first
    so the pristine source isn't mutated.

    Args:
        session: Workspace session
        path: Path to document
        revision_ids: List of revision IDs (from edit_document response)
    """
    from ..docx_xml_service import revert_tracked_changes, validate_document_xml
    from .document_tools import resolve_or_clone_to_v2

    try:

        resolved_path, cloned_from = resolve_or_clone_to_v2(session, path)
        path = resolved_path

        doc = session.get_document(path)
        if not doc:
            return {
                "success": False,
                "error": f"Document not found: {path}",
            }

        if not doc.docx_blob:
            return {
                "success": False,
                "error": f"Document {path} has no DOCX - cannot revert edits",
            }

        xml_content = doc.document_xml
        if xml_content is None:
            return {
                "success": False,
                "error": "Failed to extract XML from DOCX blob",
            }

        int_ids = [int(rid) for rid in revision_ids]
        new_xml, info = revert_tracked_changes(xml_content, int_ids)

        if info.get("error"):
            return {"success": False, "error": info["error"]}

        errors = validate_document_xml(new_xml)
        parse_errors = [e for e in errors if e.startswith("XML parse error")]
        if parse_errors:
            return {
                "success": False,
                "error": f"Revert produced invalid XML: {'; '.join(parse_errors)}",
                "validation_errors": errors,
            }

        doc.update_document_xml(new_xml)
        try:
            session.save()
        except Exception as save_err:
            logger.warning(f"[DOCX-REVERT] Session save failed: {save_err}")

        result = {
            "success": True,
            "path": path,
            "doc_type": "docx",
            "reverted_ids": info.get("reverted_ids", []),
            "not_found_ids": info.get("not_found_ids", []),
            "message": f"Reverted {len(info.get('reverted_ids', []))} tracked changes",
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
            result["message"] += f" (working copy {path} created from {cloned_from})"
        if errors:
            result["validation_warnings"] = errors
        return result

    except Exception as e:
        logger.error(f"revert_edit failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def _call_libreoffice_tracked_changes(
    docx_bytes: bytes,
    filename: str,
    op: str,                        
) -> bytes:
    """POST to libreoffice-service /tracked-changes/{op} and return bytes."""
    import os as _os
    import requests as _requests

    url = _os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
    resp = _requests.post(
        f"{url}/tracked-changes/{op}",
        files={"file": (filename, docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.content

def _call_libreoffice_compare(
    file1_bytes: bytes,
    file1_name: str,
    file2_bytes: bytes,
    file2_name: str,
) -> bytes:
    """POST to libreoffice-service /compare and return the redlined DOCX bytes."""
    import os as _os
    import requests as _requests

    url = _os.environ.get("LIBREOFFICE_SERVICE_URL", "http://localhost:8002")
    mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    resp = _requests.post(
        f"{url}/compare",
        files={
            "file1": (file1_name, file1_bytes, mime),
            "file2": (file2_name, file2_bytes, mime),
        },
        timeout=180,
    )
    resp.raise_for_status()
    return resp.content

def accept_all_changes(
    session: WorkspaceSession,
    path: str,
    output_path: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Accept all tracked changes in a DOCX via LibreOffice.

    Routes through the libreoffice-service ``/tracked-changes/accept``
    endpoint which dispatches ``.uno:AcceptAllTrackedChanges`` — the only
    reliable way to handle every OOXML edge case (nested changes, complex
    formatting, paragraph marks, content controls, comment anchors).

    Source resolution: ``path`` is routed through the same
    auto-clone-to-v2 logic ``edit_document`` uses. If ``path`` is the
    pristine original and a ``_v{N}`` working copy already exists (from
    a prior edit_document / add_comment), accept reads from the working
    copy — not the pristine source. If no working copy exists and
    ``output_path`` isn't provided, accept clones first so the pristine
    source isn't mutated.

    Args:
        session: Workspace session.
        path: Document UUID or workspace path (auto-routes to working copy).
        output_path: Optional workspace path for the cleaned result. If
            omitted, the resolved (post-auto-clone) path is updated in place.

    Returns:
        ``{"success": bool, "path": str, "remaining_changes": int, ...}``
    """
    from .document_tools import resolve_or_clone_to_v2, _find_latest_version

    try:

        cloned_from = None
        if output_path:
            resolved_source, _next = _find_latest_version(session, path)
        else:
            resolved_source, cloned_from = resolve_or_clone_to_v2(session, path)

        doc = session.get_document(resolved_source)
        if not doc:
            return {"success": False, "error": f"Document not found: {resolved_source}"}
        if not doc.docx_blob:
            return {
                "success": False,
                "error": f"Document has no DOCX blob (HTML-only): {resolved_source}",
            }
        path = resolved_source

        filename = (path.split("/")[-1] or "document.docx")
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"

        cleaned_bytes = _call_libreoffice_tracked_changes(
            doc.docx_blob, filename, "accept"
        )

        try:
            from ..docx_xml_service import extract_document_xml
            xml = extract_document_xml(cleaned_bytes)
            remaining_ins = xml.count("<w:ins ")
            remaining_del = xml.count("<w:del ")
        except Exception:
            remaining_ins = remaining_del = -1           

        if output_path:
            session.add_document(output_path, doc.content, description=doc.description)
            session.get_document(output_path).update_docx(cleaned_bytes)
            target_path = output_path
        else:
            doc.update_docx(cleaned_bytes)

            doc.mark_finalized()
            target_path = path

        session.save()

        result = {
            "success": True,
            "path": target_path,

            "doc_type": "docx",
            "remaining_insertions": remaining_ins,
            "remaining_deletions": remaining_del,
            "message": (
                f"All tracked changes accepted via LibreOffice "
                f"({remaining_ins + remaining_del if remaining_ins >= 0 else '?'} remaining)"
            ),
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
            result["message"] += f" (working copy {target_path} created from {cloned_from})"
        if not output_path:

            result["round_finalized"] = True
        return result
    except Exception as e:
        logger.error(f"accept_all_changes failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def reject_all_changes(
    session: WorkspaceSession,
    path: str,
    output_path: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Reject all tracked changes in a DOCX via LibreOffice.

    Dispatches ``.uno:RejectAllTrackedChanges``. Restores the doc to its
    pre-edit state.

    Source resolution mirrors ``accept_all_changes``: pristine-original
    paths are auto-routed to the working copy (or a new ``_v{N}`` is
    cloned when no working copy exists and no ``output_path`` is given).
    """
    from .document_tools import resolve_or_clone_to_v2, _find_latest_version

    try:
        cloned_from = None
        if output_path:
            resolved_source, _next = _find_latest_version(session, path)
        else:
            resolved_source, cloned_from = resolve_or_clone_to_v2(session, path)

        doc = session.get_document(resolved_source)
        if not doc:
            return {"success": False, "error": f"Document not found: {resolved_source}"}
        if not doc.docx_blob:
            return {"success": False, "error": f"Document has no DOCX blob: {resolved_source}"}
        path = resolved_source

        filename = (path.split("/")[-1] or "document.docx")
        if not filename.lower().endswith(".docx"):
            filename = f"{filename}.docx"

        cleaned_bytes = _call_libreoffice_tracked_changes(
            doc.docx_blob, filename, "reject"
        )

        try:
            from ..docx_xml_service import extract_document_xml
            xml = extract_document_xml(cleaned_bytes)
            remaining_ins = xml.count("<w:ins ")
            remaining_del = xml.count("<w:del ")
        except Exception:
            remaining_ins = remaining_del = -1

        if output_path:
            session.add_document(output_path, doc.content, description=doc.description)
            session.get_document(output_path).update_docx(cleaned_bytes)
            target_path = output_path
        else:
            doc.update_docx(cleaned_bytes)

            doc.mark_finalized()
            target_path = path

        session.save()

        result = {
            "success": True,
            "path": target_path,

            "doc_type": "docx",
            "remaining_insertions": remaining_ins,
            "remaining_deletions": remaining_del,
            "message": (
                f"All tracked changes rejected via LibreOffice — "
                f"original state restored"
            ),
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
            result["message"] += f" (working copy {target_path} created from {cloned_from})"
        if not output_path:
            result["round_finalized"] = True
        return result
    except Exception as e:
        logger.error(f"reject_all_changes failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def produce_redline(
    session: WorkspaceSession,
    path_a: str,
    path_b: str,
    output_path: str,
    author: str = "Anylegal.ai",
    **kwargs,
) -> Dict[str, Any]:
    """
    Produce a redlined comparison DOCX from two documents.

    Returns a new DOCX showing path_b's differences from path_a as
    tracked changes — opens directly in Word for the user to review and
    accept/reject. The redlining is done by LibreOffice's native
    ``.uno:CompareDocuments`` UNO dispatcher (paragraph-mark migration,
    run-property tracking, table-cell edge cases all handled correctly).

    Distinct from ``compare`` (text-level diff for agent reasoning).

    Args:
        session: Workspace session
        path_a: Baseline document (before)
        path_b: Revised document (after)
        output_path: Save the redlined result at this path
        author: Author name for the tracked changes

    Returns:
        ``{success, output_path, doc_type: "docx", path_a, path_b}``
    """
    try:
        if not path_a or not path_b:
            return {"success": False, "error": "Both path_a and path_b are required"}
        if not output_path:
            return {"success": False, "error": "output_path is required"}

        doc_a = session.get_document(path_a)
        doc_b = session.get_document(path_b)
        if not doc_a:
            return {"success": False, "error": f"path_a not found: {path_a}"}
        if not doc_b:
            return {"success": False, "error": f"path_b not found: {path_b}"}
        if not doc_a.docx_blob:
            return {"success": False, "error": f"path_a has no DOCX blob: {path_a}"}
        if not doc_b.docx_blob:
            return {"success": False, "error": f"path_b has no DOCX blob: {path_b}"}

        try:
            redlined_bytes = _call_libreoffice_compare(
                doc_a.docx_blob,
                _basename(path_a),
                doc_b.docx_blob,
                _basename(path_b),
            )
        except Exception as e:
            logger.error(f"libreoffice-service /compare failed: {e}")
            return {"success": False, "error": f"compare service failed: {e}"}

        if output_path in session.documents:
            existing = session.get_document(output_path)
            existing.update_docx(redlined_bytes)
        else:
            session.add_document(
                path=output_path,
                content="",
                description=f"Redline: {path_a} vs {path_b}",
                set_active=True,
            )
            session.get_document(output_path).update_docx(redlined_bytes)

        session.save()

        return {
            "success": True,
            "output_path": output_path,
            "doc_type": "docx",
            "path_a": path_a,
            "path_b": path_b,
        }

    except Exception as e:
        logger.error(f"produce_redline failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

def _basename(path: str) -> str:
    """Filename portion of a workspace path, with .docx fallback."""
    import os as _os
    name = _os.path.basename(path) or "document.docx"
    if not name.lower().endswith(".docx"):
        name = name + ".docx"
    return name

DOCX_TOOLS = {
    "revert_edit": revert_edit,
    "get_revision_stats": get_revision_stats,
    "accept_all_changes": accept_all_changes,
    "reject_all_changes": reject_all_changes,
    "accept_changes": accept_changes,
    "reject_changes": reject_changes,
    "produce_redline": produce_redline,
}
