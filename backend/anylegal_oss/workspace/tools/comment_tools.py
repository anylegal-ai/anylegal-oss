"""
Comment tool — add a margin comment to a DOCX document.

Handles the 4-file coordination Word/LibreOffice requires:
  - ``word/comments.xml``               (the comment itself)
  - ``word/commentsExtended.xml``        (threading + resolved state)
  - ``word/commentsIds.xml``             (durableId mapping)
  - ``word/commentsExtensible.xml``      (timestamps for threading)

Plus the relationships and content-types registrations, plus the comment-
range markers in ``word/document.xml``.

Ported from Anthropic's ``scripts/comment.py`` — their CLI produces markers
that the model hand-inserts; we do the marker insertion inside this tool too
so the LLM only has to call one function.

Missing files are created from the templates under ``comment_templates/``.
"""

from __future__ import annotations

import io
import logging
import os
import random
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ..session import WorkspaceSession

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "comment_templates"

COMMENTS_XML = "word/comments.xml"
COMMENTS_EXT_XML = "word/commentsExtended.xml"
COMMENTS_IDS_XML = "word/commentsIds.xml"
COMMENTS_EXTENSIBLE_XML = "word/commentsExtensible.xml"
DOCUMENT_XML = "word/document.xml"
DOCUMENT_RELS = "word/_rels/document.xml.rels"
CONTENT_TYPES = "[Content_Types].xml"

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
}

COMMENT_RELATIONSHIPS = [
    (
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
        "comments.xml",
    ),
    (
        "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
        "commentsExtended.xml",
    ),
    (
        "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
        "commentsIds.xml",
    ),
    (
        "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
        "commentsExtensible.xml",
    ),
]

COMMENT_CONTENT_TYPES = [
    (
        "/word/comments.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
    ),
    (
        "/word/commentsExtended.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
    ),
    (
        "/word/commentsIds.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml",
    ),
    (
        "/word/commentsExtensible.xml",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml",
    ),
]

def _hex_id() -> str:
    return f"{random.randint(0, 0x7FFFFFFE):08X}"

def _template(name: str) -> bytes:
    path = TEMPLATE_DIR / name
    return path.read_bytes()

def _zip_to_dict(docx_bytes: bytes) -> Dict[str, bytes]:
    """Load a DOCX into a dict of {part_name: bytes}."""
    parts: Dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        for name in zf.namelist():
            parts[name] = zf.read(name)
    return parts

def _dict_to_zip(parts: Dict[str, bytes]) -> bytes:
    """Rebuild a DOCX from a parts dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in parts.items():
            zf.writestr(name, content)
    return buf.getvalue()

def _escape_xml_text(text: str) -> str:
    """XML-escape comment body text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def _next_comment_id(comments_xml_bytes: bytes) -> int:
    """Find next available w:id in comments.xml."""
    try:
        ids = [
            int(m.group(1))
            for m in re.finditer(rb'<w:comment\b[^>]*\bw:id="(\d+)"', comments_xml_bytes)
        ]
        return (max(ids) + 1) if ids else 0
    except Exception:
        return 0

def _ensure_comment_parts(parts: Dict[str, bytes]) -> None:
    """Create any missing comment parts from templates."""
    if COMMENTS_XML not in parts:
        parts[COMMENTS_XML] = _template("comments.xml")
    if COMMENTS_EXT_XML not in parts:
        parts[COMMENTS_EXT_XML] = _template("commentsExtended.xml")
    if COMMENTS_IDS_XML not in parts:
        parts[COMMENTS_IDS_XML] = _template("commentsIds.xml")
    if COMMENTS_EXTENSIBLE_XML not in parts:
        parts[COMMENTS_EXTENSIBLE_XML] = _template("commentsExtensible.xml")

def _next_rid(rels_bytes: bytes) -> int:
    ids = [
        int(m.group(1))
        for m in re.finditer(rb'\bId="rId(\d+)"', rels_bytes)
    ]
    return (max(ids) + 1) if ids else 1

def _ensure_comment_relationships(parts: Dict[str, bytes]) -> None:
    """Register the comment XML parts in word/_rels/document.xml.rels."""
    if DOCUMENT_RELS not in parts:

        return
    rels = parts[DOCUMENT_RELS].decode("utf-8")

    missing = [
        (rtype, target)
        for (rtype, target) in COMMENT_RELATIONSHIPS
        if f'Target="{target}"' not in rels
    ]
    if not missing:
        return

    next_rid = _next_rid(parts[DOCUMENT_RELS])
    new_rels = []
    for rtype, target in missing:
        new_rels.append(
            f'<Relationship Id="rId{next_rid}" Type="{rtype}" Target="{target}"/>'
        )
        next_rid += 1

    rels = rels.replace(
        "</Relationships>", "".join(new_rels) + "</Relationships>"
    )
    parts[DOCUMENT_RELS] = rels.encode("utf-8")

def _ensure_comment_content_types(parts: Dict[str, bytes]) -> None:
    """Register the comment parts in [Content_Types].xml."""
    if CONTENT_TYPES not in parts:
        return
    ct = parts[CONTENT_TYPES].decode("utf-8")
    missing = [
        (pn, ctype)
        for (pn, ctype) in COMMENT_CONTENT_TYPES
        if f'PartName="{pn}"' not in ct
    ]
    if not missing:
        return

    overrides = "".join(
        f'<Override PartName="{pn}" ContentType="{ctype}"/>' for (pn, ctype) in missing
    )
    ct = ct.replace("</Types>", overrides + "</Types>")
    parts[CONTENT_TYPES] = ct.encode("utf-8")

def _append_comment_xml(
    parts: Dict[str, bytes],
    comment_id: int,
    author: str,
    initials: str,
    text: str,
    para_id: str,
    date: str,
) -> None:
    """Append a <w:comment> element to comments.xml."""
    escaped = _escape_xml_text(text)
    escaped_author = _escape_xml_text(author)
    comment_el = (
        f'<w:comment w:id="{comment_id}" w:author="{escaped_author}" '
        f'w:date="{date}" w:initials="{initials}">'
        f'<w:p w14:paraId="{para_id}" w14:textId="77777777">'
        f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
        f'<w:annotationRef/></w:r>'
        f'<w:r><w:rPr><w:color w:val="000000"/><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
        f'<w:t>{escaped}</w:t></w:r>'
        f'</w:p></w:comment>'
    )
    comments = parts[COMMENTS_XML].decode("utf-8")
    comments = comments.replace("</w:comments>", comment_el + "</w:comments>")
    parts[COMMENTS_XML] = comments.encode("utf-8")

def _append_extended(
    parts: Dict[str, bytes], para_id: str, parent_para_id: Optional[str]
) -> None:
    ext = parts[COMMENTS_EXT_XML].decode("utf-8")
    if parent_para_id:
        el = (
            f'<w15:commentEx w15:paraId="{para_id}" '
            f'w15:paraIdParent="{parent_para_id}" w15:done="0"/>'
        )
    else:
        el = f'<w15:commentEx w15:paraId="{para_id}" w15:done="0"/>'
    ext = ext.replace("</w15:commentsEx>", el + "</w15:commentsEx>")
    parts[COMMENTS_EXT_XML] = ext.encode("utf-8")

def _append_ids(parts: Dict[str, bytes], para_id: str, durable_id: str) -> None:
    ids = parts[COMMENTS_IDS_XML].decode("utf-8")
    el = f'<w16cid:commentId w16cid:paraId="{para_id}" w16cid:durableId="{durable_id}"/>'
    ids = ids.replace("</w16cid:commentsIds>", el + "</w16cid:commentsIds>")
    parts[COMMENTS_IDS_XML] = ids.encode("utf-8")

def _append_extensible(parts: Dict[str, bytes], durable_id: str, date: str) -> None:
    ext = parts[COMMENTS_EXTENSIBLE_XML].decode("utf-8")
    el = f'<w16cex:commentExtensible w16cex:durableId="{durable_id}" w16cex:dateUtc="{date}"/>'
    ext = ext.replace("</w16cex:commentsExtensible>", el + "</w16cex:commentsExtensible>")
    parts[COMMENTS_EXTENSIBLE_XML] = ext.encode("utf-8")

def _find_parent_para_id(parts: Dict[str, bytes], parent_id: int) -> Optional[str]:
    """Look up the paraId of a parent comment (for reply threading)."""
    comments = parts[COMMENTS_XML].decode("utf-8")
    m = re.search(
        rf'<w:comment\b[^>]*\bw:id="{parent_id}".*?w14:paraId="([0-9A-Fa-f]+)"',
        comments,
        re.DOTALL,
    )
    return m.group(1) if m else None

def _insert_markers_in_document(
    parts: Dict[str, bytes],
    target_text: str,
    comment_id: int,
    near_text: Optional[str],
) -> tuple[bool, str]:
    """Wrap a text span in document.xml with commentRangeStart/End + reference."""
    doc = parts[DOCUMENT_XML].decode("utf-8")

    pattern = re.compile(
        r'(<w:r\b[^>]*>(?:(?!</w:r>).)*?<w:t\b[^>]*>[^<]*'
        + re.escape(target_text)
        + r'[^<]*</w:t>(?:(?!</w:r>).)*?</w:r>)',
        re.DOTALL,
    )
    matches = list(pattern.finditer(doc))
    if not matches:
        return False, f"target_text not found as contiguous run text: {target_text!r}"

    if len(matches) > 1:
        if near_text and near_text in doc:
            near_pos = doc.index(near_text)
            chosen = min(matches, key=lambda m: abs(m.start() - near_pos))
        else:
            return (
                False,
                f"target_text matches {len(matches)} locations; pass near_text to disambiguate",
            )
    else:
        chosen = matches[0]

    start_marker = f'<w:commentRangeStart w:id="{comment_id}"/>'
    end_marker = f'<w:commentRangeEnd w:id="{comment_id}"/>'
    reference = (
        f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
        f'<w:commentReference w:id="{comment_id}"/></w:r>'
    )

    wrapped = start_marker + chosen.group(0) + end_marker + reference
    doc = doc[: chosen.start()] + wrapped + doc[chosen.end():]
    parts[DOCUMENT_XML] = doc.encode("utf-8")
    return True, ""

def add_comment(
    session: WorkspaceSession,
    path: str,
    target_text: str,
    comment_text: str,
    author: str = "Anylegal.ai",
    initials: str = "A",
    parent_id: Optional[int] = None,
    near_text: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Add a margin comment to a DOCX document.

    Args:
        session: WorkspaceSession.
        path: Document UUID or workspace path.
        target_text: Text in the document body to anchor the comment to. The
              comment balloon appears next to this text in Word.
        comment_text: The comment content (what the user sees in the margin).
        author: Comment author. Defaults to "Anylegal.ai".
        initials: Author initials (2-3 chars). Defaults to "A".
        parent_id: Reply-to-comment-id for threaded replies. Omit for a new
              top-level comment.
        near_text: Disambiguator when ``target_text`` appears multiple times.

    Returns:
        ``{"success", "path", "comment_id", "para_id", "durable_id", "message"}``
    """
    try:

        from .document_tools import resolve_or_clone_to_v2
        resolved_path, cloned_from = resolve_or_clone_to_v2(session, path)
        path = resolved_path

        doc = session.get_document(path)
        if not doc:
            return {"success": False, "error": f"Document not found: {path}"}
        if not doc.docx_blob:
            return {"success": False, "error": f"Document has no DOCX blob: {path}"}
        if not target_text:
            return {"success": False, "error": "target_text is required"}
        if not comment_text:
            return {"success": False, "error": "comment_text is required"}

        parts = _zip_to_dict(doc.docx_blob)
        _ensure_comment_parts(parts)
        _ensure_comment_relationships(parts)
        _ensure_comment_content_types(parts)

        comment_id = _next_comment_id(parts[COMMENTS_XML])
        para_id = _hex_id()
        durable_id = _hex_id()
        date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        parent_para_id: Optional[str] = None
        if parent_id is not None:
            parent_para_id = _find_parent_para_id(parts, parent_id)
            if not parent_para_id:
                return {
                    "success": False,
                    "error": f"Parent comment {parent_id} not found",
                }

        _append_comment_xml(
            parts=parts,
            comment_id=comment_id,
            author=author,
            initials=initials,
            text=comment_text,
            para_id=para_id,
            date=date,
        )
        _append_extended(parts, para_id, parent_para_id)
        _append_ids(parts, para_id, durable_id)
        _append_extensible(parts, durable_id, date)

        ok, err = _insert_markers_in_document(
            parts=parts,
            target_text=target_text,
            comment_id=comment_id,
            near_text=near_text,
        )
        if not ok:
            return {"success": False, "error": err}

        new_blob = _dict_to_zip(parts)

        try:
            from .validators.docx_validator import validate_docx_output
            validation = validate_docx_output(new_blob, level="full")
            if validation.get("repaired_bytes"):
                new_blob = validation["repaired_bytes"]
            if validation.get("errors"):
                logger.warning(
                    f"add_comment validation warnings: {validation['errors']}"
                )
        except Exception as e:
            logger.debug(f"post-comment validation skipped: {e}")

        doc.update_docx(new_blob)
        session.save()

        result = {
            "success": True,
            "path": path,

            "doc_type": "docx",
            "comment_id": comment_id,
            "para_id": para_id,
            "durable_id": durable_id,
            "author": author,
            "is_reply": parent_id is not None,
            "message": (
                f"Added {'reply' if parent_id is not None else 'comment'} "
                f"(id={comment_id}) on '{target_text[:40]}'"
            ),
        }
        if cloned_from:
            result["cloned_from"] = cloned_from
            result["message"] = (
                f"First mutation on '{cloned_from}' — created working copy "
                f"'{path}' and added comment (id={comment_id}) on "
                f"'{target_text[:40]}'. Original preserved."
            )
        return result
    except Exception as e:
        logger.error(f"add_comment failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

COMMENT_TOOLS = {
    "add_comment": add_comment,
}
