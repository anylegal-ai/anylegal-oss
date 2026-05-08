"""
DOCX validation and auto-repair toolkit.

Two generations of validators live here:

- ``docx_validator`` (level="full"|"light") — the unified entry point used by
  ``run_python`` post-hook and ``edit_document`` path. Orchestrates fast
  structural checks (well-formed XML, tracked-change rules, whitespace) and
  — at level="full" — delegates to the heavier XSD validators below.
- ``DOCXSchemaValidator`` / ``RedliningValidator`` (ported from Anthropic's
  docx skill) — XSD-schema-based validation with auto-repair for paraId /
  durableId and whitespace preservation. Operates on an unpacked directory
  of the DOCX ZIP.
- ``simplify_redlines`` — helper that merges adjacent <w:ins>/<w:del> from
  the same author, called after every ``apply_text_edit`` /
  ``apply_range_delete``.
- ``docx_fixer`` — LLM-output auto-fix (colors, emojis, empty paragraphs).
  Runs before validation on ``run_python`` output.
"""

from .docx_fixer import auto_fix_docx
from .docx_validator import validate_docx_output
from .simplify_redlines import simplify_redlines, infer_author
from .xsd_base import BaseSchemaValidator
from .xsd_docx import DOCXSchemaValidator
from .redlining_xsd import RedliningValidator

__all__ = [
    "auto_fix_docx",
    "validate_docx_output",
    "simplify_redlines",
    "infer_author",
    "BaseSchemaValidator",
    "DOCXSchemaValidator",
    "RedliningValidator",
]
