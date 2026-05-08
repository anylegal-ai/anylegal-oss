"""
Legal Analysis Tool Implementations

Helpers for the agentic LLM — no LLM calls here. The model does the reasoning;
these tools just retrieve or transform data.

Active tool:
- compare — diff two texts or two workspace documents; returns structured
  diff, similarity %, and visual output (html/markdown/summary).
"""

import logging
from typing import Any, Dict, Optional

from ..session import WorkspaceSession

logger = logging.getLogger(__name__)

def compare(
    text_a: Optional[str] = None,
    text_b: Optional[str] = None,
    path_a: Optional[str] = None,
    path_b: Optional[str] = None,
    format: str = "summary",
    session: Optional[WorkspaceSession] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Compare two texts or two session documents.

    Accepts direct text strings OR document paths. Returns structured diff,
    similarity %, and visual output.
    """
    content_a = text_a
    content_b = text_b

    def _content_from_doc(doc):
        """Prefer DOCX-extracted plain text over the HTML body so two DOCX
        docs diff against extracted prose, not against HTML markup that
        would generate noise from formatting differences."""
        if getattr(doc, "docx_blob", None):
            try:
                from ..docx_xml_service import extract_plain_text
                return extract_plain_text(doc.docx_blob)
            except Exception:
                pass
        return doc.content

    if path_a and not content_a:
        if not session:
            return {"success": False, "error": "Session required to read document paths"}
        doc_a = session.get_document(path_a)
        if not doc_a:
            return {
                "success": False,
                "error": f"Document not found: {path_a}",
                "available": list(session.documents.keys()),
            }
        content_a = _content_from_doc(doc_a)

    if path_b and not content_b:
        if not session:
            return {"success": False, "error": "Session required to read document paths"}
        doc_b = session.get_document(path_b)
        if not doc_b:
            return {
                "success": False,
                "error": f"Document not found: {path_b}",
                "available": list(session.documents.keys()),
            }
        content_b = _content_from_doc(doc_b)

    if not content_a or not content_b:
        return {
            "success": False,
            "error": "Two texts required (provide text_a/text_b or path_a/path_b)",
        }

    return _fallback_compare(content_a, content_b, path_a or "(text)", path_b or "(text)", format)

def _fallback_compare(
    content_a: str,
    content_b: str,
    path_a: str,
    path_b: str,
    format: str,
) -> Dict[str, Any]:
    """Document comparison using diff_tool module."""
    from .diff_tool import (
        compare_texts_tool,
        render_html_redline,
        render_plaintext_redline,
    )

    comparison = compare_texts_tool(content_a, content_b)
    summary = comparison["summary"]

    if format == "summary":
        return {
            "success": True,
            "path_a": path_a,
            "path_b": path_b,
            "additions": summary["insertions"],
            "deletions": summary["deletions"],
            "inserted_chars": summary["inserted_chars"],
            "deleted_chars": summary["deleted_chars"],
            "similarity_percent": comparison["similarity_percent"],
            "summary": f"{summary['insertions']} additions, {summary['deletions']} deletions",
        }
    elif format == "markdown":
        plaintext = render_plaintext_redline(content_a, content_b, word_level=True)
        return {
            "success": True,
            "path_a": path_a,
            "path_b": path_b,
            "diff": plaintext,
            "summary": summary,
        }
    else:        
        html_diff = render_html_redline(content_a, content_b, word_level=True)
        return {
            "success": True,
            "path_a": path_a,
            "path_b": path_b,
            "diff_html": html_diff,
            "summary": summary,
        }

LEGAL_TOOLS = {
    "compare": compare,
}
