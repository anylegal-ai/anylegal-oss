"""
DOCX Auto-Fixer

Programmatically fixes common formatting mistakes that LLMs make:
1. Colored text → black
2. Empty spacing paragraphs → removed (replaced by space_after on preceding paragraph)
3. Soft line breaks (\n within a paragraph) used for alignment → removed where inappropriate
4. Emojis → removed

Runs automatically after every run_python DOCX output, before validation.
"""

import logging
import re
import zipfile
from io import BytesIO
from typing import List, Tuple

logger = logging.getLogger(__name__)

def auto_fix_docx(docx_bytes: bytes, is_new_document: bool = True) -> Tuple[bytes, List[str]]:
    """
    Auto-fix common formatting issues in a DOCX file.

    Args:
        docx_bytes: The DOCX file bytes
        is_new_document: True if created from scratch (safe to remove empty paragraphs).
                         False if modifying an existing/uploaded document (preserve structure).

    Returns:
        (fixed_bytes, list_of_fixes_applied)
    """
    fixes = []

    try:
        xml_str = _extract_document_xml(docx_bytes)
    except Exception:
        return docx_bytes, []

    original_xml = xml_str

    xml_str, color_fixes = _fix_colors(xml_str)
    if color_fixes:
        fixes.append(f"Fixed {color_fixes} non-black text colors to black")

    xml_str, emoji_fixes = _fix_emojis(xml_str)
    if emoji_fixes:
        fixes.append(f"Removed {emoji_fixes} emoji characters")

    if is_new_document:
        xml_str, empty_fixes = _fix_empty_paragraphs(xml_str)
        if empty_fixes:
            fixes.append(f"Removed {empty_fixes} empty spacing paragraphs")

    if not fixes:
        return docx_bytes, []

    fixed_bytes = _rebuild_docx(docx_bytes, xml_str)
    return fixed_bytes, fixes

def _extract_document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(docx_bytes)) as zf:
        return zf.read("word/document.xml").decode("utf-8")

def _rebuild_docx(original_bytes: bytes, new_xml: str) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(BytesIO(original_bytes)) as zin:
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))
    return output.getvalue()

def _fix_del_text_elements(xml_str: str) -> Tuple[str, int]:
    """Fix <w:t> inside <w:del> → <w:delText>. This is the #1 cause of Word 'unreadable content'."""
    count = 0

    def _fix_del_block(match):
        nonlocal count
        full = match.group(0)
        inner = match.group(1)

        result = []
        pos = 0
        ins_depth = 0

        while pos < len(inner):

            ins_open = re.match(r'<w:ins\b[^>]*>', inner[pos:])
            if ins_open:
                ins_depth += 1
                result.append(ins_open.group(0))
                pos += ins_open.end()
                continue

            ins_close = re.match(r'</w:ins>', inner[pos:])
            if ins_close:
                ins_depth -= 1
                result.append(ins_close.group(0))
                pos += ins_close.end()
                continue

            if ins_depth == 0:
                t_match = re.match(r'<w:t(\b[^>]*)>([^<]*)</w:t>', inner[pos:])
                if t_match:
                    attrs = t_match.group(1)
                    text = t_match.group(2)
                    if text.strip():                        
                        count += 1
                    result.append(f'<w:delText{attrs}>{text}</w:delText>')
                    pos += t_match.end()
                    continue

            result.append(inner[pos])
            pos += 1

        return f'<w:del{match.group(0)[len("<w:del"):len(match.group(0))-len(inner)-len("</w:del>")]}{"".join(result)}</w:del>'

    def _simple_fix(match):
        nonlocal count
        attrs = match.group(1)
        inner = match.group(2)

        ins_blocks = {}
        ins_idx = 0

        def _save_ins(m):
            nonlocal ins_idx
            key = f'__INS_PLACEHOLDER_{ins_idx}__'
            ins_blocks[key] = m.group(0)
            ins_idx += 1
            return key

        cleaned = re.sub(r'<w:ins\b[^>]*>.*?</w:ins>', _save_ins, inner, flags=re.DOTALL)

        def _replace_t(m):
            nonlocal count
            t_attrs = m.group(1)
            text = m.group(2)
            if text.strip():
                count += 1
            return f'<w:delText{t_attrs}>{text}</w:delText>'

        fixed = re.sub(r'<w:t(\b[^>]*)>([^<]*)</w:t>', _replace_t, cleaned)

        for key, block in ins_blocks.items():
            fixed = fixed.replace(key, block)

        return f'<w:del{attrs}>{fixed}</w:del>'

    xml_str = re.sub(r'<w:del(\b[^>]*)>(.*?)</w:del>', _simple_fix, xml_str, flags=re.DOTALL)
    return xml_str, count

def _fix_colors(xml_str: str) -> Tuple[str, int]:
    """Replace all non-black <w:color> values with black."""
    count = 0

    def _replace_color(match):
        nonlocal count
        val = match.group(1)
        if val not in ('000000', 'auto', 'Auto'):
            count += 1
            return '<w:color w:val="000000"'
        return match.group(0)

    xml_str = re.sub(r'<w:color w:val="([^"]+)"', _replace_color, xml_str)
    return xml_str, count

def _fix_emojis(xml_str: str) -> Tuple[str, int]:
    """Remove emoji characters from <w:t> content."""
    emoji_pattern = re.compile(
        '[\U0001F300-\U0001F9FF'
        '\U00002702-\U000027B0'
        '\U0000FE00-\U0000FE0F'
        '\U0000200D'
        '\U00002600-\U000026FF'
        '\U00002B50-\U00002B55'
        '\U0000231A-\U0000231B'
        '\U00002934-\U00002935'
        '\U000025AA-\U000025FE'
        '\U00002139'
        '\U00003030\U0000303D'
        '\U0001F680-\U0001F6FF'
        ']+'
    )

    count = 0

    def _clean_text(match):
        nonlocal count
        attrs = match.group(1)
        text = match.group(2)
        cleaned = emoji_pattern.sub('', text)
        if cleaned != text:
            count += len(emoji_pattern.findall(text))
        return f'<w:t{attrs}>{cleaned}</w:t>'

    xml_str = re.sub(r'<w:t([^>]*)>([^<]*)</w:t>', _clean_text, xml_str)
    return xml_str, count

def _fix_empty_paragraphs(xml_str: str) -> Tuple[str, int]:
    """Remove empty paragraphs used for spacing (keep ones with tracked changes)."""
    count = 0

    def _check_para(match):
        nonlocal count
        full = match.group(0)
        inner = match.group(1)

        if '<w:del ' in inner or '<w:ins ' in inner:
            return full

        texts = re.findall(r'<w:t[^>]*>([^<]*)</w:t>', inner)
        if any(t.strip() for t in texts):
            return full

        if '<w:r>' in inner or '<w:r ' in inner:

            has_real_content = bool(re.search(
                r'<w:(drawing|pict|br|tab|sym|footnoteReference|endnoteReference)',
                inner
            ))
            if has_real_content:
                return full

        count += 1
        return ''

    xml_str = re.sub(r'<w:p\b[^>]*>(.*?)</w:p>', _check_para, xml_str, flags=re.DOTALL)

    xml_str = re.sub(r'\n\s*\n\s*\n', '\n\n', xml_str)

    return xml_str, count
