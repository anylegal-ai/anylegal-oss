"""
DOCX Validator — unified entry point.

Two validation levels:

- ``level="light"`` (fast, ~10-30ms): well-formed XML, w:del/w:delText rule,
  w:ins/w:delText rule, whitespace preservation, basic ID constraints.
  Called by the ``edit_document`` path after every tracked-change edit.

- ``level="full"`` (thorough, ~200-500ms on big docs): everything in light
  plus XSD schema validation, namespace checks, unique-ID checks, rels
  cross-check, content-types validation, paraId/durableId auto-repair,
  comment marker pairing, paragraph-count diff. Called by ``run_python``
  post-hook when the sandbox produces a DOCX file.

Both levels run the ``RedliningValidator`` (strip author's tracked changes,
compare plain text against the original) when ``original_bytes`` is supplied.
Redlining runs at both levels because it catches the ``edit_document``
failure mode specifically.

Auto-fixer runs BEFORE validation (see ``docx_fixer.py``) — it patches the
things the LLM breaks every time (colors, emojis, empty paragraphs) so they
don't surface as validation errors.
"""

import logging
import os
import re
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from .xsd_base import _safe_zip_extract

logger = logging.getLogger(__name__)

REQUIRED_PARTS = [
    "[Content_Types].xml",
    "word/document.xml",
]

def validate_docx_output(
    docx_bytes: bytes,
    original_bytes: Optional[bytes] = None,
    author: str = "Anylegal.ai",
    level: str = "full",
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    Validate a DOCX file at the requested depth.

    Args:
        docx_bytes: The DOCX blob to validate.
        original_bytes: Optional original DOCX for redlining diff validation.
        author: Author name for tracked changes (redlining validator strips
                this author's changes before comparing).
        level: ``"light"`` or ``"full"``. See module docstring.
        verbose: Pass through to the XSD validators.

    Returns:
        {
          "valid": bool,
          "level": "light" | "full",
          "errors": [str, ...],
          "warnings": [str, ...],
          "repairs_made": int,    # only populated at level="full"
          "repaired_bytes": bytes | None,  # non-None if repairs succeeded
        }
    """
    if level not in ("light", "full"):
        raise ValueError(f"level must be 'light' or 'full', got {level!r}")

    errors: List[str] = []
    warnings: List[str] = []
    repairs_made = 0
    repaired_bytes: Optional[bytes] = None

    if not _validate_package(docx_bytes, errors):
        return _result(False, level, errors, warnings, 0, None)

    try:
        xml_str = _extract_document_xml(docx_bytes)
    except Exception as e:
        errors.append(f"Failed to extract word/document.xml: {e}")
        return _result(False, level, errors, warnings, 0, None)

    try:
        from xml.dom.minidom import parseString
        parseString(xml_str.encode("utf-8"))
    except Exception as e:
        errors.append(f"XML parse error: {e}")
        return _result(False, level, errors, warnings, 0, None)

    _validate_tracked_changes(xml_str, errors)

    _validate_whitespace(xml_str, warnings)

    _validate_ids(xml_str, warnings)

    _validate_formatting(xml_str, warnings)

    if original_bytes:
        _validate_redlining(
            docx_bytes=docx_bytes,
            original_bytes=original_bytes,
            author=author,
            errors=errors,
        )

    if level == "light":
        return _result(not errors, level, errors, warnings, 0, None)

    with tempfile.TemporaryDirectory(prefix="anylegal_validate_") as td:
        unpacked_dir = Path(td) / "unpacked"
        unpacked_dir.mkdir()
        try:
            with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
                _safe_zip_extract(zf, unpacked_dir)
        except Exception as e:
            errors.append(f"Failed to unpack DOCX for full validation: {e}")
            return _result(False, level, errors, warnings, 0, None)

        original_path: Optional[Path] = None
        if original_bytes:
            original_path = Path(td) / "original.docx"
            original_path.write_bytes(original_bytes)

        try:
            from .xsd_docx import DOCXSchemaValidator
            validator = DOCXSchemaValidator(
                unpacked_dir=unpacked_dir,
                original_file=original_path,
                verbose=verbose,
            )

            try:
                repairs_made = validator.repair()
            except Exception as e:
                logger.warning(f"XSD auto-repair failed (non-fatal): {e}")
                repairs_made = 0

            if repairs_made > 0:
                try:
                    repaired_bytes = _repack_dir_to_bytes(unpacked_dir)
                except Exception as e:
                    logger.warning(f"Re-zip after repair failed: {e}")
                    repaired_bytes = None

            try:
                xsd_ok = validator.validate()
                if not xsd_ok:

                    errors.append(
                        "XSD/schema validation failed — see stdout for "
                        "per-error details."
                    )
            except Exception as e:
                logger.warning(f"XSD validation exception (non-fatal): {e}")
                errors.append(f"XSD validator error: {e}")

        except ImportError as e:
            logger.warning(f"XSD validators not available: {e}")

    return _result(not errors, level, errors, warnings, repairs_made, repaired_bytes)

def _result(
    valid: bool,
    level: str,
    errors: List[str],
    warnings: List[str],
    repairs_made: int,
    repaired_bytes: Optional[bytes],
) -> Dict[str, Any]:
    return {
        "valid": valid,
        "level": level,
        "errors": errors,
        "warnings": warnings,
        "repairs_made": repairs_made,
        "repaired_bytes": repaired_bytes,
    }

def _validate_package(docx_bytes: bytes, errors: List[str]) -> bool:
    try:
        with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
            names = zf.namelist()
            for part in REQUIRED_PARTS:
                if part not in names:
                    errors.append(f"Missing required part: {part}")
            return len(errors) == 0
    except zipfile.BadZipFile:
        errors.append("Not a valid ZIP file (corrupt DOCX)")
        return False
    except Exception as e:
        errors.append(f"Failed to open DOCX: {e}")
        return False

def _extract_document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        return zf.read("word/document.xml").decode("utf-8")

def _validate_tracked_changes(xml_str: str, errors: List[str]) -> None:
    """<w:del> must use <w:delText>; <w:ins> must not contain <w:delText>
    outside a nested <w:del>."""
    try:
        from ...docx_xml_service import validate_document_xml
        xml_errors = validate_document_xml(xml_str)
        errors.extend(xml_errors)
        return
    except ImportError:
        pass

    del_blocks = re.findall(r'<w:del\b[^>]*>(.*?)</w:del>', xml_str, re.DOTALL)
    for block in del_blocks:
        cleaned = re.sub(r'<w:ins\b[^>]*>.*?</w:ins>', '', block, flags=re.DOTALL)
        t_matches = re.findall(r'<w:t\b[^>]*>(.*?)</w:t>', cleaned, re.DOTALL)
        for t_text in t_matches:
            if t_text.strip():
                errors.append(
                    f"<w:t> inside <w:del> (should be <w:delText>): '{t_text[:50]}'"
                )

def _validate_whitespace(xml_str: str, warnings: List[str]) -> None:
    for match in re.finditer(r'<w:t(?P<attrs>[^>]*)>(?P<text>[^<]*)</w:t>', xml_str):
        attrs = match.group("attrs")
        text = match.group("text")
        if text and (text[0] in ' \t' or text[-1] in ' \t'):
            if 'xml:space="preserve"' not in attrs:
                warnings.append(
                    f"<w:t> with whitespace missing xml:space='preserve': '{text[:30]}'"
                )

def _validate_ids(xml_str: str, warnings: List[str]) -> None:
    for match in re.finditer(r'w14:paraId="([^"]+)"', xml_str):
        try:
            val = int(match.group(1), 16)
            if val >= 0x80000000:
                warnings.append(f"paraId {match.group(1)} exceeds 0x7FFFFFFF")
        except ValueError:
            pass

    for match in re.finditer(r'w15:durableId="([^"]+)"', xml_str):
        try:
            val = int(match.group(1))
            if val >= 0x7FFFFFFF:
                warnings.append(f"durableId {match.group(1)} exceeds 0x7FFFFFFF")
        except ValueError:
            pass

def _validate_formatting(xml_str: str, warnings: List[str]) -> None:
    """Flag non-justified body paragraphs — can't be safely auto-fixed."""
    body_paras = 0
    justified_paras = 0
    for match in re.finditer(r'<w:p\b[^>]*>(.*?)</w:p>', xml_str, re.DOTALL):
        inner = match.group(1)
        if '<w:pStyle' in inner:
            style_match = re.search(r'<w:pStyle w:val="([^"]+)"', inner)
            if style_match:
                style = style_match.group(1)
                if any(s in style for s in ('Heading', 'Title', 'TOC', 'Header', 'Footer')):
                    continue
        texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', inner)
        if any(t.strip() for t in texts):
            body_paras += 1
            if '<w:jc w:val="both"' in inner:
                justified_paras += 1

    if body_paras > 10 and justified_paras < body_paras * 0.5:
        warnings.append(
            f"Only {justified_paras}/{body_paras} body paragraphs are justified. "
            f"Legal documents should use justified alignment (WD_ALIGN_PARAGRAPH.JUSTIFY)."
        )

def _validate_redlining(
    docx_bytes: bytes,
    original_bytes: bytes,
    author: str,
    errors: List[str],
) -> None:
    """Run the Anthropic-style RedliningValidator in a tmp dir.

    Writes both docx files to a temp dir, unpacks the modified one, and
    runs the validator. Produces git word-diff on failure.
    """
    try:
        from .redlining_xsd import RedliningValidator
    except ImportError:
        logger.debug("RedliningValidator not available; skipping redlining check")
        return

    try:
        with tempfile.TemporaryDirectory(prefix="anylegal_redline_") as td:
            td_path = Path(td)
            original_path = td_path / "original.docx"
            original_path.write_bytes(original_bytes)

            unpacked = td_path / "unpacked"
            unpacked.mkdir()
            with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
                _safe_zip_extract(zf, unpacked)

            import io
            import contextlib
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                validator = RedliningValidator(
                    unpacked_dir=unpacked,
                    original_docx=original_path,
                    author=author,
                )
                ok = validator.validate()

            if not ok:
                output = captured.getvalue()

                first_line = output.splitlines()[0] if output else "redlining failed"
                errors.append(
                    f"Redlining validation failed: {first_line}. "
                    f"Text outside tracked changes differs from original — "
                    f"the model likely edited text without wrapping it in "
                    f"<w:ins>/<w:del>."
                )
    except Exception as e:
        logger.warning(f"Redlining validator exception (non-fatal): {e}")

def _repack_dir_to_bytes(unpacked_dir: Path) -> bytes:
    """Zip an unpacked DOCX directory back into bytes."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in unpacked_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(unpacked_dir))
    return buf.getvalue()

def _strip_tracked_changes(xml_str: str, author: str) -> str:
    """
    Strip all tracked changes by the specified author from a document.xml
    string:
      - ``<w:ins w:author="author">`` blocks: removed entirely.
      - ``<w:del w:author="author">`` blocks: unwrapped (content kept,
        ``<w:delText>`` renamed to ``<w:t>``).

    Used by the redlining validator's pre-compaction step and by tests that
    exercise the author-filter logic in isolation.
    """
    result = re.sub(
        rf'<w:ins\b[^>]*w:author="{re.escape(author)}"[^>]*>.*?</w:ins>',
        '',
        xml_str,
        flags=re.DOTALL,
    )

    def _unwrap_del(match: re.Match) -> str:
        inner = match.group(1)
        inner = re.sub(r'<w:delText\b', '<w:t', inner)
        inner = re.sub(r'</w:delText>', '</w:t>', inner)
        return inner

    result = re.sub(
        rf'<w:del\b[^>]*w:author="{re.escape(author)}"[^>]*>(.*?)</w:del>',
        _unwrap_del,
        result,
        flags=re.DOTALL,
    )
    return result

def _rebuild_docx_with_xml(original_bytes: bytes, new_xml: str) -> bytes:
    """Replace ``word/document.xml`` in ``original_bytes`` with ``new_xml``."""
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(original_bytes)) as zin:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))
    return output.getvalue()
