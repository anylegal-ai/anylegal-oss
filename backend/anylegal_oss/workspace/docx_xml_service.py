"""
DOCX XML Service — In-memory unpack / merge-runs / validate / repack / edit.

Adapts the Anthropic DOCX Skill workflow (unpack → edit XML → pack) for
server-side agentic editing.  Instead of writing to disk, every operation
works on bytes/strings in memory.

Public API
----------
extract_document_xml(blob) → str
    Extract word/document.xml, pretty-print, merge runs, strip RSIDs.
    Returns the cleaned XML string for LLM consumption.

repack_docx(original_blob, new_document_xml) → bytes
    Replace word/document.xml inside the DOCX ZIP and return new blob.

validate_document_xml(xml_str) → list[str]
    Quick structural checks (well-formed, w:del uses w:delText, etc.).

apply_text_edit(xml_str, old_text, new_text, author) → (str, dict) | (None, dict)
    Find plain text in <w:t> elements and apply tracked-change markup.
    The LLM sends plain text; this function generates OOXML w:del/w:ins.
"""

import io
import logging
import re
import zipfile
from datetime import datetime, timezone
from defusedxml.minidom import parseString as safe_parseString
from xml.dom import minidom                                            

logger = logging.getLogger(__name__)

SMART_QUOTE_REPLACEMENTS = {
    "\u201c": "&#x201C;",                     
    "\u201d": "&#x201D;",                      
    "\u2018": "&#x2018;",                     
    "\u2019": "&#x2019;",                                   
}

def extract_document_xml(blob: bytes) -> str:
    """
    Extract ``word/document.xml`` from a DOCX blob, clean it up, and return
    a pretty-printed XML string suitable for LLM editing.

    Processing steps (mirrors Anthropic DOCX Skill ``unpack.py``):
    1. Extract document.xml from ZIP
    2. Pretty-print for readability
    3. Remove ``<w:proofErr>`` elements (spell-check noise)
    4. Strip ``rsid`` attributes from runs (revision-save IDs — noise)
    5. Merge adjacent ``<w:r>`` elements with identical formatting
    6. Escape smart quotes to XML entities
    """
    raw_xml = _read_zip_entry(blob, "word/document.xml")

    dom = safe_parseString(raw_xml)
    root = dom.documentElement

    _remove_elements(root, "proofErr")
    _strip_run_rsid_attrs(root)

    containers = {run.parentNode for run in _find_elements(root, "r")}
    merge_count = 0
    for container in containers:
        merge_count += _merge_runs_in(container)

    xml_str = dom.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")

    for char, entity in SMART_QUOTE_REPLACEMENTS.items():
        xml_str = xml_str.replace(char, entity)

    xml_str = re.sub(r'\n\s*\n', '\n', xml_str)

    logger.info(f"[DOCX-XML] Extracted document.xml: merged {merge_count} runs")
    return xml_str

def repack_docx(original_blob: bytes, new_document_xml: str) -> bytes:
    """
    Replace ``word/document.xml`` inside the DOCX ZIP with *new_document_xml*
    and return the updated DOCX blob.

    All other ZIP entries (styles, media, rels, etc.) are preserved unchanged.
    The XML is condensed (whitespace between tags removed) before packing to
    keep the file size reasonable.
    """
    condensed_xml = _condense_xml(new_document_xml)

    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original_blob), "r") as zin:
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, condensed_xml.encode("utf-8"))
                else:
                    zout.writestr(item, zin.read(item.filename))

    return output.getvalue()

def validate_document_xml(xml_str: str) -> list:
    """
    Quick structural validation of document.xml after LLM editing.

    Checks:
    1. XML is well-formed (parses without errors)
    2. ``<w:del>`` contains ``<w:delText>`` not ``<w:t>``
    3. ``<w:ins>`` does not contain ``<w:delText>`` (unless nested in ``<w:del>``)
    4. ``<w:t>`` with leading/trailing whitespace has ``xml:space="preserve"``

    Returns list of error strings (empty = valid).
    """
    errors = []

    try:
        dom = safe_parseString(xml_str.encode("utf-8"))
    except Exception as e:
        return [f"XML parse error: {e}"]

    root = dom.documentElement

    for del_elem in _find_elements(root, "del"):
        for t_elem in _find_elements(del_elem, "t"):

            parent = t_elem.parentNode
            inside_ins = False
            while parent and parent != del_elem:
                name = parent.localName or parent.tagName
                if name == "ins" or name.endswith(":ins"):
                    inside_ins = True
                    break
                parent = parent.parentNode
            if not inside_ins:
                text = _get_text_content(t_elem)[:50]
                errors.append(
                    f"<w:t> inside <w:del> (should be <w:delText>): '{text}'"
                )

    for ins_elem in _find_elements(root, "ins"):
        for dt_elem in _find_elements(ins_elem, "delText"):
            parent = dt_elem.parentNode
            inside_del = False
            while parent and parent != ins_elem:
                name = parent.localName or parent.tagName
                if name == "del" or name.endswith(":del"):
                    inside_del = True
                    break
                parent = parent.parentNode
            if not inside_del:
                text = _get_text_content(dt_elem)[:50]
                errors.append(
                    f"<w:delText> inside <w:ins> without <w:del>: '{text}'"
                )

    for t_elem in _find_elements(root, "t"):
        text = _get_text_content(t_elem)
        if text and (text[0] in ' \t' or text[-1] in ' \t'):
            if t_elem.getAttribute("xml:space") != "preserve":
                errors.append(
                    f"<w:t> with whitespace missing xml:space='preserve': "
                    f"'{text[:30]}'"
                )

    return errors

def extract_plain_text(blob: bytes) -> str:
    """
    Extract plain text from a DOCX blob for LLM analysis.

    Returns paragraph text joined by double newlines.  Tables are rendered
    with ``|`` cell separators so the LLM can see the structure and avoid
    trying to match text that spans across table cells.
    """
    raw_xml = _read_zip_entry(blob, "word/document.xml")
    dom = safe_parseString(raw_xml)
    root = dom.documentElement

    def _para_text(p_elem) -> str:
        """Extract text from a single <w:p>, skipping deleted content."""
        texts: list = []
        for r_elem in _find_elements(p_elem, "r"):
            if _is_inside_del_dom(r_elem):
                continue
            for child in r_elem.childNodes:
                if child.nodeType != child.ELEMENT_NODE:
                    continue
                tag = child.localName or child.tagName or ""
                if tag == "t" or tag.endswith(":t"):
                    text = _get_text_content(child)
                    if text:
                        texts.append(text)
                elif tag == "br" or tag.endswith(":br"):
                    texts.append("\n")
        return "".join(texts)

    def _table_text(tbl_elem) -> str:
        """Render a <w:tbl> as pipe-delimited rows."""
        rows: list = []
        for tr_elem in _find_elements(tbl_elem, "tr"):
            cells: list = []
            for tc_elem in _find_elements(tr_elem, "tc"):

                cell_paras = [
                    _para_text(p) for p in _find_elements(tc_elem, "p")
                ]
                cell_text = " ".join(t for t in cell_paras if t.strip())
                cells.append(cell_text.strip())
            if any(cells):
                rows.append("| " + " | ".join(cells) + " |")
        return "\n".join(rows)

    body = None
    for child in root.childNodes:
        if child.nodeType != child.ELEMENT_NODE:
            continue
        tag = child.localName or child.tagName or ""
        if tag == "body" or tag.endswith(":body"):
            body = child
            break
    if body is None:
        body = root            

    blocks: list = []
    for child in body.childNodes:
        if child.nodeType != child.ELEMENT_NODE:
            continue
        tag = child.localName or child.tagName or ""
        if tag == "p" or tag.endswith(":p"):
            pt = _para_text(child)
            if pt.strip():
                blocks.append(pt)
        elif tag == "tbl" or tag.endswith(":tbl"):
            tt = _table_text(child)
            if tt.strip():
                blocks.append(tt)

    return "\n\n".join(blocks)

def revert_tracked_changes(
    xml_str: str,
    revision_ids: list,
) -> tuple:
    """
    Surgically remove specific tracked changes from DOCX XML by revision ID.

    For each revision ID:
    - ``<w:del w:id="ID">`` → **unwrap**: convert ``<w:delText>`` to ``<w:t>``,
      remove the ``<w:del>`` wrapper, keep the ``<w:r>`` children as normal text.
    - ``<w:ins w:id="ID">`` → **remove entirely** (the inserted text disappears).

    After removal, empty paragraphs (``<w:p>`` with only ``<w:pPr>`` and no runs)
    are cleaned up — these arise from cross-paragraph edits that added extra
    INS-only paragraphs.

    Parameters
    ----------
    xml_str : str
        Current document.xml content (may contain multiple edits).
    revision_ids : list of int
        Exact revision IDs from the ``edit_document`` response.

    Returns
    -------
    (new_xml, info_dict)
        info_dict contains ``reverted_ids``, ``not_found_ids``.
    """
    if not revision_ids:
        return xml_str, {"error": "No revision IDs provided"}

    id_set = set(int(rid) for rid in revision_ids)
    reverted = []
    not_found = []
    result = xml_str

    for rid in sorted(id_set):
        rid_str = str(rid)

        ins_pattern = re.compile(
            rf'<w:ins\b[^>]*w:id="{rid_str}"[^>]*>.*?</w:ins>',
            re.DOTALL,
        )
        ins_match = ins_pattern.search(result)
        if ins_match:
            result = result[:ins_match.start()] + result[ins_match.end():]
            reverted.append(rid)

        del_pattern = re.compile(
            rf'<w:del\b[^>]*w:id="{rid_str}"[^>]*>(.*?)</w:del>',
            re.DOTALL,
        )
        del_match = del_pattern.search(result)
        if del_match:
            inner = del_match.group(1)

            restored = re.sub(r'<w:delText\b', '<w:t', inner)
            restored = restored.replace('</w:delText>', '</w:t>')
            result = result[:del_match.start()] + restored + result[del_match.end():]
            if rid not in reverted:
                reverted.append(rid)

        if rid not in reverted:
            not_found.append(rid)

    result = _remove_empty_paragraphs(result)

    info = {"reverted_ids": reverted, "not_found_ids": not_found}
    return result, info

def accept_specific_changes(
    xml_str: str,
    revision_ids: list,
) -> tuple:
    """
    Accept specific tracked changes by revision ID.

    For each revision ID:
    - ``<w:ins w:id="ID">`` → **unwrap**: keep the ``<w:r>`` children as
      plain text (the insertion is now permanent).
    - ``<w:del w:id="ID">`` → **remove entirely** (the deleted text
      stays gone).

    After removal, empty paragraphs (those left containing only
    ``<w:pPr>``) are cleaned up.

    Mirror of ``revert_tracked_changes`` — same shape, opposite intent.
    Use this when the lawyer says "accept this change"; use revert/reject
    when they say "undo this change".

    Returns
    -------
    (new_xml, info_dict)
        info_dict contains ``accepted_ids``, ``not_found_ids``.
    """
    if not revision_ids:
        return xml_str, {"error": "No revision IDs provided"}

    id_set = set(int(rid) for rid in revision_ids)
    accepted = []
    not_found = []
    result = xml_str

    for rid in sorted(id_set):
        rid_str = str(rid)
        landed = False

        ins_pattern = re.compile(
            rf'<w:ins\b[^>]*w:id="{rid_str}"[^>]*>(.*?)</w:ins>',
            re.DOTALL,
        )
        ins_match = ins_pattern.search(result)
        if ins_match:
            inner = ins_match.group(1)
            result = result[:ins_match.start()] + inner + result[ins_match.end():]
            landed = True

        del_pattern = re.compile(
            rf'<w:del\b[^>]*w:id="{rid_str}"[^>]*>.*?</w:del>',
            re.DOTALL,
        )
        del_match = del_pattern.search(result)
        if del_match:
            result = result[:del_match.start()] + result[del_match.end():]
            landed = True

        if landed:
            accepted.append(rid)
        else:
            not_found.append(rid)

    result = _remove_empty_paragraphs(result)

    return result, {"accepted_ids": accepted, "not_found_ids": not_found}

def _remove_empty_paragraphs(xml_str: str) -> str:
    """Remove ``<w:p>`` elements that contain no runs after revert cleanup.

    A paragraph is considered empty and removable when it has no ``<w:r>``
    elements and no ``<w:t>`` / ``<w:delText>`` elements — i.e. it contains
    only ``<w:pPr>`` and whitespace.  This happens when a cross-paragraph
    INS-only paragraph is reverted (the ``<w:ins>`` is removed, leaving an
    empty ``<w:p>``).
    """
    result = xml_str
    para_re = re.compile(r'<w:p\b[^>]*>.*?</w:p>', re.DOTALL)

    for m in reversed(list(para_re.finditer(result))):
        para = m.group(0)
        if not re.search(r'<w:r\b', para):
            result = result[:m.start()] + result[m.end():]
    return result

_XML_ENTITY_DECODE = {
    "&#x201C;": "\u201c",                     
    "&#x201D;": "\u201d",                      
    "&#x2018;": "\u2018",                     
    "&#x2019;": "\u2019",                      
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&apos;": "'",
}

def _delete_empty_paragraph_marks(
    xml_str: str,
    revision_ids: list,
    author: str = "Anylegal.ai",
) -> tuple:
    """Mark paragraph marks as deleted for paragraphs emptied by tracked changes.

    When ``apply_text_edit`` or ``apply_range_delete`` wraps *all* text of a
    paragraph in ``<w:del>`` (pure deletion, no ``<w:ins>``), Word keeps the
    paragraph mark (¶) visible — creating blank lines both in tracked-change
    view and after accepting.  The OOXML fix is to add
    ``<w:rPr><w:del .../></w:rPr>`` inside ``<w:pPr>``, which tells Word the
    paragraph mark itself is deleted and should collapse when accepted.

    Only processes paragraphs that:
      1. Contain at least one of our *revision_ids*
      2. Have at least one ``<w:del>`` block (were actually edited)
      3. Have **no** visible text (no ``<w:t>`` outside ``<w:del>``, no ``<w:ins>``)

    Returns ``(modified_xml, extra_revision_ids)``.
    """
    if not revision_ids:
        return xml_str, []

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rev_strs = {str(rid) for rid in revision_ids}
    next_id = max(revision_ids) + 1
    extra_ids = []

    p_re = re.compile(r"(<w:p\b[^>]*>)(.*?)(</w:p>)", re.DOTALL)
    t_re = re.compile(r"<w:t\b[^>]*>[^<]*</w:t>", re.DOTALL)
    ins_re = re.compile(r"<w:ins\b")
    del_re = re.compile(r"<w:del\b")

    result_parts = []
    last_end = 0

    for m in p_re.finditer(xml_str):
        p_open, p_body, p_close = m.group(1), m.group(2), m.group(3)

        if not any(f'w:id="{rid}"' in p_body for rid in rev_strs):
            continue

        if not del_re.search(p_body):
            continue

        if ins_re.search(p_body):
            continue

        has_visible_t = False
        for t_m in t_re.finditer(p_body):
            if not _is_inside_del_str(p_body, t_m.start()):
                has_visible_t = True
                break
        if has_visible_t:
            continue

        ppr_re = re.compile(r"<w:pPr\b[^>]*>(.*?)</w:pPr>", re.DOTALL)
        ppr_m = ppr_re.search(p_body)
        if ppr_m and "<w:del " in ppr_m.group(1):
            continue                                       

        del_attr = (
            f'w:id="{next_id}" w:author="{author}" w:date="{date_str}"'
        )

        if ppr_m:

            ppr_content = ppr_m.group(1)
            rpr_re = re.compile(r"(<w:rPr\b[^>]*>)(.*?)(</w:rPr>)", re.DOTALL)
            rpr_m = rpr_re.search(ppr_content)
            if rpr_m:

                new_rpr = (
                    rpr_m.group(1)
                    + rpr_m.group(2)
                    + f"<w:del {del_attr}/>"
                    + rpr_m.group(3)
                )
                new_ppr_inner = (
                    ppr_content[: rpr_m.start()]
                    + new_rpr
                    + ppr_content[rpr_m.end() :]
                )
            else:
                new_ppr_inner = (
                    ppr_content + f"<w:rPr><w:del {del_attr}/></w:rPr>"
                )
            new_ppr = ppr_m.group(0).replace(ppr_m.group(1), new_ppr_inner, 1)
            new_body = p_body[: ppr_m.start()] + new_ppr + p_body[ppr_m.end() :]
        else:

            new_body = (
                f"<w:pPr><w:rPr><w:del {del_attr}/></w:rPr></w:pPr>" + p_body
            )

        new_p = p_open + new_body + p_close
        result_parts.append(xml_str[last_end : m.start()])
        result_parts.append(new_p)
        last_end = m.end()
        extra_ids.append(next_id)
        next_id += 1

    if not extra_ids:
        return xml_str, []

    result_parts.append(xml_str[last_end:])
    return "".join(result_parts), extra_ids

def _finalize_edit(result_xml: str, info: dict, author: str = "Anylegal.ai"):
    """Post-process a successful edit:
    1. Delete paragraph marks for emptied paragraphs.
    2. Merge adjacent <w:ins>/<w:del> from the same author so iterative
       edits don't fragment the markup. Ported from Anthropic's
       simplify_redlines helper."""
    result_xml, extra_ids = _delete_empty_paragraph_marks(
        result_xml, info.get("revision_ids", []), author
    )
    if extra_ids:
        info["revision_ids"] = info.get("revision_ids", []) + extra_ids

    try:
        from .tools.validators.simplify_redlines import simplify_redlines_xml
        result_xml, merged = simplify_redlines_xml(result_xml)
        if merged:
            info["simplified_redlines"] = merged
            logger.debug(f"[DOCX-XML] simplified {merged} adjacent tracked changes")
    except Exception as e:
        logger.debug(f"[DOCX-XML] simplify_redlines skipped: {e}")

    return result_xml, info

def apply_text_edit(
    xml_str: str,
    old_text: str,
    new_text: str,
    author: str = "Anylegal.ai",
    near_text: str = "",
) -> tuple:
    """
    Find plain text inside ``<w:t>`` elements and apply an OOXML tracked change.

    The LLM sends human-readable *old_text* / *new_text*.  This function
    locates the text in the XML, splits the enclosing ``<w:r>``, and generates
    ``<w:del>`` / ``<w:ins>`` markup preserving the original formatting.

    Matching strategy (first match wins):
      1. Single-run: exact / quote-normalised / case-insensitive match
         within one ``<w:t>`` element.
      2. Cross-run: concatenate all ``<w:t>`` texts in a paragraph,
         match across run boundaries, preserve per-run formatting in
         the ``<w:del>`` block.
      3. Cross-paragraph: concatenate paragraph texts with separators,
         match across ``<w:p>`` boundaries.  Matched paragraphs become
         ``<w:del>`` blocks; new text is split into ``<w:ins>`` paragraphs.

    When *old_text* matches multiple locations (e.g., identical table cells),
    *near_text* disambiguates by selecting the match closest to it.

    Returns
    -------
    (new_xml_str, info_dict)  on success
    (None, error_dict)        on failure
    """
    if not old_text:
        return None, {"error": "old_text is empty"}

    tc_ranges = _skip_ranges(xml_str)

    t_re = re.compile(r"<w:t([^>]*)>([^<]*)</w:t>", re.DOTALL)

    for mode in ("exact", "quotes", "icase"):
        candidates = _scan_for_match(xml_str, t_re, tc_ranges, old_text, mode)
        if candidates:
            candidate = _resolve_candidates(xml_str, candidates, near_text, "run_span")
            if candidate is None:
                return None, _ambiguity_error(old_text, len(candidates))
            result_xml, info = _build_single_run_change(xml_str, candidate, new_text, author)
            info.setdefault("mode", f"single_run_{mode}")
            return _finalize_edit(result_xml, info, author)

    cross_candidates = _scan_cross_run(xml_str, t_re, tc_ranges, old_text)
    if cross_candidates:
        cross = _resolve_candidates(xml_str, cross_candidates, near_text, "p_start")
        if cross is None:
            return None, _ambiguity_error(old_text, len(cross_candidates))
        result_xml, info = _build_cross_run_change(xml_str, cross, new_text, author)
        info.setdefault("mode", "cross_run")
        return _finalize_edit(result_xml, info, author)

    cross_para = _scan_cross_paragraph(xml_str, t_re, tc_ranges, old_text)
    if cross_para is not None:
        result_xml, info = _build_cross_paragraph_change(
            xml_str, cross_para, new_text, author
        )
        info["mode"] = "cross_paragraph"
        return _finalize_edit(result_xml, info, author)

    nearby = _nearby_paragraph_text(xml_str, old_text)

    looks_like_table_row = (
        (" | " in old_text or old_text.lstrip().startswith("|"))
        and old_text.count("|") >= 2
    )

    partial = _longest_matching_span(xml_str, old_text) if not looks_like_table_row else None

    glyph_hint = _diagnose_glyph_mismatch(old_text)

    if looks_like_table_row:
        suggestion = (
            "Your old_text contains | pipe characters from the table display format. "
            "Table cells are separate elements — you CANNOT edit across cells in one call. "
            "Remove all | characters and edit ONE cell at a time. "
            "Example: instead of '| cell1 | cell2 |', use just 'cell1' as old_text."
        )
    elif partial and len(partial) >= 12:
        suggestion = (
            f"Your old_text is too long — the document matches a shorter span. "
            f"The longest matching segment is: '{partial[:120]}'. "
            "Retry with just that text as old_text, and if you need more "
            "context to disambiguate, pass near_text instead of extending "
            "old_text. Stretching old_text across paragraph boundaries or "
            "across a footnote / bookmark anchor is the #1 cause of "
            "'Text not found' errors."
        )
    elif glyph_hint:
        suggestion = (
            f"{glyph_hint} "
            "Retry with the exact character from the document. Use "
            "read_document(view='text') to see the source verbatim."
        )
    else:
        suggestion = (
            "The text you sent does not match the document. Checklist: "
            "(a) use read_document(view='text') and copy the EXACT span — "
            "don't retype from memory; "
            "(b) if the text spans punctuation like brackets, footnote "
            "anchors, or bookmarks, try a SHORTER span that stops before "
            "the anchor, then use near_text to disambiguate; "
            "(c) confirm special characters (● vs •, smart vs straight "
            "quotes, em vs en dash) match the source."
        )

    return None, {
        "error": f"Text not found in document: '{old_text[:120]}'",
        "suggestion": suggestion,
        "nearby_text": nearby,
        "longest_matching_prefix": partial,
    }

def _longest_matching_span(xml_str: str, old_text: str) -> str | None:
    """Find the longest prefix / suffix / substring of ``old_text`` that
    *is* present in the document's `<w:t>` text. Used to diagnose
    "model over-reached on old_text" failures — the returned span is a
    valid `old_text` the model can retry with.

    Caps at 30 candidates per direction to keep this cheap on long
    paragraphs. Returns ``None`` if no 12+ char substring matches.
    """
    if len(old_text) < 12:
        return None

    t_re = re.compile(r"<w:t[^>]*>([^<]*)</w:t>", re.DOTALL)
    tc_ranges = _skip_ranges(xml_str)
    chunks = []
    for m in t_re.finditer(xml_str):
        if _in_tracked_change(m.start(), tc_ranges):
            continue
        decoded = _decode_xml_text(m.group(1))
        if decoded:
            chunks.append(decoded)
    concat = "".join(chunks)
    if not concat:
        return None

    max_try = min(len(old_text), 400)            
    best = None

    for length in range(max_try, 11, -max(1, max_try // 30)):
        candidate = old_text[:length].rstrip()
        if len(candidate) < 12:
            continue
        if candidate in concat or candidate.lower() in concat.lower():
            best = candidate
            break
    return best

def _diagnose_glyph_mismatch(old_text: str) -> str | None:
    """Return a hint string if ``old_text`` contains characters that
    LLMs commonly substitute for the actual document character. Returns
    ``None`` if no confusables are present.
    """
    hints = []
    if "●" in old_text or "•" in old_text:
        hints.append(
            "Bullet glyphs vary — documents may use ● (U+25CF), • (U+2022), "
            "or ◦ (U+25E6); these are not interchangeable in exact-text "
            "matching."
        )
    if "—" in old_text or "–" in old_text or "―" in old_text:
        hints.append(
            "Dashes vary — em dash (—), en dash (–), and hyphen-minus (-) "
            "are different characters."
        )
    if "“" in old_text or "”" in old_text or "‘" in old_text or "’" in old_text:
        hints.append(
            "Smart quotes — the document may use straight (\" ') or "
            "curly (“ ” ‘ ’) quotes; exact match distinguishes them."
        )
    return " ".join(hints) if hints else None

def apply_range_delete(
    xml_str: str,
    start_text: str,
    end_text: str,
    author: str = "Anylegal.ai",
) -> tuple:
    """
    Delete all paragraphs from the one containing *start_text* through the
    one containing *end_text* (inclusive).

    Each matched paragraph's runs are converted to ``<w:del>`` blocks with
    ``<w:delText>``.  Paragraphs that are already fully deleted (only contain
    ``<w:del>`` content) or are empty are left as-is.

    Returns ``(new_xml_str, info_dict)`` on success, ``(None, error_dict)``
    on failure.
    """
    if not start_text or not end_text:
        return None, {"error": "Both start_text and end_text are required."}

    tc_ranges = _skip_ranges(xml_str)
    p_re = re.compile(r"<w:p\b[^>]*>.*?</w:p>", re.DOTALL)
    t_re = re.compile(r"<w:t([^>]*)>([^<]*)</w:t>", re.DOTALL)
    t_br_re = re.compile(
        r"<w:t([^>]*)>([^<]*)</w:t>|<w:br\b[^/]*/>",
        re.DOTALL,
    )

    paras = []
    for p_match in p_re.finditer(xml_str):
        p_xml = p_match.group(0)
        texts = []
        for m in t_br_re.finditer(p_xml):
            abs_pos = p_match.start() + m.start()
            if _in_tracked_change(abs_pos, tc_ranges):
                continue
            if m.group(2) is not None:
                decoded = _decode_xml_text(m.group(2))
                if decoded:
                    texts.append(decoded)
            else:
                texts.append("\n")
        paras.append({
            "text": "".join(texts),
            "p_start": p_match.start(),
            "p_end": p_match.end(),
            "p_xml": p_xml,
        })

    start_idx = None
    for i, p in enumerate(paras):
        if not p["text"].strip():
            continue
        if _text_contains(p["text"], start_text):
            start_idx = i
            break

    if start_idx is None:
        return None, {
            "error": f"Start marker not found: '{start_text[:120]}'",
            "suggestion": "Copy exact text from the document.",
        }

    end_idx = None
    for i in range(len(paras) - 1, start_idx - 1, -1):
        if not paras[i]["text"].strip():
            continue
        if _text_contains(paras[i]["text"], end_text):
            end_idx = i
            break

    if end_idx is None:
        return None, {
            "error": f"End marker not found: '{end_text[:120]}'",
            "suggestion": "Copy exact text from the document.",
        }

    if end_idx < start_idx:
        return None, {
            "error": "End marker appears before start marker.",
        }

    next_id = _next_revision_id(xml_str)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    id_counter = next_id
    revision_ids = []

    replacements = []
    for i in range(start_idx, end_idx + 1):
        p = paras[i]
        para_text = p["text"].strip()
        if not para_text:
            continue                         

        p_xml = p["p_xml"]
        non_del_text = []
        for m in t_re.finditer(p_xml):
            abs_pos = p["p_start"] + m.start()
            if not _in_tracked_change(abs_pos, tc_ranges):
                non_del_text.append(_decode_xml_text(m.group(2)))
        if not "".join(non_del_text).strip():
            continue                   

        ppr = _extract_ppr_str(p_xml)
        sp = _space_attr(para_text)
        rpr = ""

        for m in t_re.finditer(p_xml):
            abs_pos = p["p_start"] + m.start()
            if _in_tracked_change(abs_pos, tc_ranges):
                continue
            try:
                rs, re_ = _find_enclosing_run(xml_str, abs_pos)
                rpr = _extract_rpr_str(xml_str[rs:re_])
            except ValueError:
                pass
            break

        del_para = (
            f"<w:p>{ppr}"
            f'<w:del w:id="{id_counter}" w:author="{author}" w:date="{date_str}">'
            f"<w:r>{rpr}<w:delText{sp}>{_xml_escape_text(para_text)}</w:delText></w:r>"
            f"</w:del>"
            f"</w:p>"
        )
        replacements.append((p["p_start"], p["p_end"], del_para))
        revision_ids.append(id_counter)
        id_counter += 1

    if not replacements:
        return None, {"error": "No content to delete in the specified range."}

    new_xml = xml_str
    for p_start, p_end, del_para in reversed(replacements):
        new_xml = new_xml[:p_start] + del_para + new_xml[p_end:]

    info = {
        "mode": "range_delete",
        "matched_text": f"[{len(replacements)} paragraphs deleted]",
        "revision_ids": revision_ids,
        "paragraphs_deleted": len(replacements),
    }
    return _finalize_edit(new_xml, info, author)

def _text_contains(haystack: str, needle: str) -> bool:
    """Check if *haystack* contains *needle* with normalisation fallbacks."""
    if needle in haystack:
        return True
    norm_h = _normalize_quotes(haystack)
    norm_n = _normalize_quotes(needle)
    if norm_n in norm_h:
        return True
    if norm_n.lower() in norm_h.lower():
        return True
    return False

def _build_single_run_change(xml_str, candidate, new_text, author):
    """Build tracked change for text found within a single ``<w:r>``.

    If the matched run is inside an existing ``<w:ins>`` block, the text is
    updated in-place (amending the insertion) rather than nesting tracked
    changes, which matches how Word handles edits to unaccepted insertions.
    """
    run_start, run_end = candidate["run_span"]
    run_xml = xml_str[run_start:run_end]
    rpr = _extract_rpr_str(run_xml)

    actual_old = candidate["actual_old"]
    prefix = candidate["prefix"]
    suffix = candidate["suffix"]

    inside_ins = _is_inside_ins(run_start, xml_str)

    if inside_ins:

        ins_lines = [l for l in new_text.split('\n') if l.strip()] if new_text and '\n' in new_text else []
        ins_multiline = len(ins_lines) > 1

        if ins_multiline:

            try:
                p_start, p_end = _find_enclosing_paragraph(xml_str, run_start)
                para_xml = xml_str[p_start:p_end]
                ppr = _extract_ppr_str(para_xml)

                ins_re = re.compile(r"<w:ins\b[^>]*>", re.DOTALL)
                ins_tag = None
                for im in ins_re.finditer(xml_str):
                    if im.start() <= run_start:
                        ins_end = xml_str.find("</w:ins>", im.start())
                        if ins_end != -1 and ins_end >= run_end:
                            ins_tag = im.group(0)
                ins_open = ins_tag or '<w:ins w:id="0" w:author="Anylegal.ai">'

                before_run = xml_str[p_start:run_start]
                after_run = xml_str[run_end:p_end]

                first_p = before_run
                if prefix:
                    sp = _space_attr(prefix)
                    first_p += f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(prefix)}</w:t></w:r>"
                first_p += _build_ins_runs(ins_lines[0], rpr)
                if suffix:
                    sp = _space_attr(suffix)
                    first_p += f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(suffix)}</w:t></w:r>"
                first_p += after_run

                paras = [first_p]

                base_rpr = _strip_rpr_bold(rpr)
                base_ppr = _strip_ppr_numbering(ppr)
                for line in ins_lines[1:]:
                    new_p = (
                        f"<w:p>{base_ppr}"
                        f"{ins_open}"
                        + _build_ins_runs(line, base_rpr)
                        + "</w:ins>"
                        "</w:p>"
                    )
                    paras.append(new_p)

                replacement = "".join(paras)
                new_xml = xml_str[:p_start] + replacement + xml_str[p_end:]

                return new_xml, {
                    "matched_text": actual_old,
                    "replacement_text": new_text,
                    "mode": "ins_amend_multiline",
                    "paragraphs_added": len(ins_lines) - 1,
                }
            except ValueError:
                pass                                              

        parts = []

        if prefix:
            sp = _space_attr(prefix)
            parts.append(f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(prefix)}</w:t></w:r>")

        if new_text:
            parts.append(_build_ins_runs(new_text, rpr))

        if suffix:
            sp = _space_attr(suffix)
            parts.append(f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(suffix)}</w:t></w:r>")

        replacement = "".join(parts)
        new_xml = xml_str[:run_start] + replacement + xml_str[run_end:]

        return new_xml, {
            "matched_text": actual_old,
            "replacement_text": new_text,
            "mode": "ins_amend",
        }

    next_id = _next_revision_id(xml_str)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [l for l in new_text.split('\n') if l.strip()] if new_text and '\n' in new_text else []
    multiline = len(lines) > 1

    if multiline:

        try:
            p_start, p_end = _find_enclosing_paragraph(xml_str, run_start)
            para_xml = xml_str[p_start:p_end]
            ppr = _extract_ppr_str(para_xml)

            before_run = xml_str[p_start:run_start]
            after_run = xml_str[run_end:p_end]

            paras = []

            first_p = before_run
            if prefix:
                sp = _space_attr(prefix)
                first_p += f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(prefix)}</w:t></w:r>"

            sp_d = _space_attr(actual_old)
            first_p += (
                f'<w:del w:id="{next_id}" w:author="{author}" w:date="{date_str}">'
                f"<w:r>{rpr}<w:delText{sp_d}>{_xml_escape_text(actual_old)}</w:delText></w:r>"
                f"</w:del>"
            )

            first_p += (
                f'<w:ins w:id="{next_id + 1}" w:author="{author}" w:date="{date_str}">'
                + _build_ins_runs(lines[0], rpr)
                + "</w:ins>"
            )

            if suffix:
                sp = _space_attr(suffix)
                first_p += f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(suffix)}</w:t></w:r>"

            first_p += after_run                                         
            paras.append(first_p)

            base_rpr = _strip_rpr_bold(rpr)
            base_ppr = _strip_ppr_numbering(ppr)
            for i, line in enumerate(lines[1:], start=2):
                ins_id = next_id + i
                new_p = (
                    f"<w:p>{base_ppr}"
                    f'<w:ins w:id="{ins_id}" w:author="{author}" w:date="{date_str}">'
                    + _build_ins_runs(line, base_rpr)
                    + "</w:ins>"
                    "</w:p>"
                )
                paras.append(new_p)

            replacement = "".join(paras)
            new_xml = xml_str[:p_start] + replacement + xml_str[p_end:]

            return new_xml, {
                "matched_text": actual_old,
                "replacement_text": new_text,
                "paragraphs_added": len(lines) - 1,
                "revision_ids": list(range(next_id, next_id + len(lines) + 1)),
            }
        except ValueError:
            pass                                                

    parts = []

    if prefix:
        sp = _space_attr(prefix)
        parts.append(f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(prefix)}</w:t></w:r>")

    sp_d = _space_attr(actual_old)
    parts.append(
        f'<w:del w:id="{next_id}" w:author="{author}" w:date="{date_str}">'
        f"<w:r>{rpr}<w:delText{sp_d}>{_xml_escape_text(actual_old)}</w:delText></w:r>"
        f"</w:del>"
    )

    if new_text:
        parts.append(
            f'<w:ins w:id="{next_id + 1}" w:author="{author}" w:date="{date_str}">'
            + _build_ins_runs(new_text, rpr)
            + "</w:ins>"
        )

    if suffix:
        sp = _space_attr(suffix)
        parts.append(f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(suffix)}</w:t></w:r>")

    replacement = "".join(parts)
    new_xml = xml_str[:run_start] + replacement + xml_str[run_end:]

    return new_xml, {
        "matched_text": actual_old,
        "replacement_text": new_text,
        "revision_ids": [next_id] + ([next_id + 1] if new_text else []),
    }

def _scan_cross_run(xml_str, t_re, tc_ranges, old_text):
    """
    Search for *old_text* spanning multiple ``<w:r>`` elements within a
    single paragraph.

    Returns a **list** of candidate dicts (empty if no matches).
    """
    p_re = re.compile(r"<w:p\b[^>]*>(.*?)</w:p>", re.DOTALL)

    t_br_re = re.compile(
        r"<w:t([^>]*)>([^<]*)</w:t>|<w:br\b[^/]*/>",
        re.DOTALL,
    )

    candidates = []

    for p_match in p_re.finditer(xml_str):
        p_content = p_match.group(1)
        p_offset = p_match.start(1)

        runs = []
        concat = ""

        for m in t_br_re.finditer(p_content):
            abs_pos = p_offset + m.start()
            if _in_tracked_change(abs_pos, tc_ranges):
                continue

            if m.group(2) is not None:

                decoded = _decode_xml_text(m.group(2))
                if not decoded:
                    continue

                try:
                    run_start, run_end = _find_enclosing_run(xml_str, abs_pos)
                except ValueError:
                    continue

                rpr = _extract_rpr_str(xml_str[run_start:run_end])

                runs.append({
                    "decoded": decoded,
                    "text_start": len(concat),
                    "text_end": len(concat) + len(decoded),
                    "run_start": run_start,
                    "run_end": run_end,
                    "rpr": rpr,
                })
                concat += decoded
            else:

                if runs:
                    runs[-1]["decoded"] += "\n"
                    runs[-1]["text_end"] += 1
                concat += "\n"

        if len(runs) < 2:
            continue

        match_pos = _find_in_paragraph(concat, old_text)
        if match_pos is None:
            continue

        match_start, actual_old = match_pos
        match_end = match_start + len(actual_old)

        start_idx = end_idx = None
        for i, run in enumerate(runs):
            if start_idx is None and run["text_end"] > match_start:
                start_idx = i
            if run["text_start"] < match_end:
                end_idx = i

        if start_idx is None or end_idx is None or start_idx == end_idx:
            continue                                                    

        candidates.append({
            "runs": runs,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "match_start": match_start,
            "match_end": match_end,
            "actual_old": actual_old,
            "p_start": p_match.start(),
        })

    return candidates

def _normalize_for_match(text: str) -> str:
    """Apply all normalisations: quotes + whitespace + symbols."""
    return _normalize_whitespace(_normalize_quotes(_normalize_symbols(text)))

def _find_in_paragraph(concat, old_text):
    """
    Try to find *old_text* in concatenated paragraph text.

    Returns ``(start_pos, actual_old_text)`` or ``None``.
    Uses exact → normalised → case-insensitive → whitespace-agnostic fallback.
    """

    if old_text in concat:
        return (concat.index(old_text), old_text)

    norm_old = _normalize_for_match(old_text)
    norm_concat = _normalize_for_match(concat)
    if norm_old in norm_concat:
        idx = norm_concat.index(norm_old)
        return (idx, concat[idx : idx + len(old_text)])

    lower_old = norm_old.lower()
    lower_concat = norm_concat.lower()
    if lower_old in lower_concat:
        idx = lower_concat.index(lower_old)
        return (idx, concat[idx : idx + len(old_text)])

    result = _find_whitespace_agnostic(concat, old_text)
    if result is not None:
        return result

    return _find_fillblank_agnostic(concat, old_text)

def _find_whitespace_agnostic(concat, old_text):
    """Match ``old_text`` against ``concat`` ignoring whitespace.

    Returns ``(start_pos_in_concat, actual_old_text_in_concat)`` or ``None``.
    The returned ``actual`` span is the raw (whitespace-preserving) slice of
    ``concat`` — so downstream tracked-change generation operates on exactly
    the text the document stores, not the LLM's reshaped version.
    """

    norm_old = _normalize_for_match(old_text)
    norm_concat = _normalize_for_match(concat)

    stripped_chars = []
    index_map = []
    for i, ch in enumerate(norm_concat):
        if not ch.isspace():
            stripped_chars.append(ch)
            index_map.append(i)
    stripped_concat = "".join(stripped_chars)

    stripped_old = "".join(c for c in norm_old if not c.isspace())
    if not stripped_old:
        return None

    pos = stripped_concat.find(stripped_old)
    if pos < 0:
        pos = stripped_concat.lower().find(stripped_old.lower())
    if pos < 0:
        return None

    concat_start = index_map[pos]
    concat_end_char = index_map[pos + len(stripped_old) - 1]

    concat_end = concat_end_char + 1
    actual = concat[concat_start:concat_end]
    return (concat_start, actual)

_FILLBLANK_RUN_RE = re.compile(
    r"(?:[.…․‥·_]\s*){1,}[.…․‥·_]"
    r"|[.…․‥·_]{2,}"
)

def _find_fillblank_agnostic(concat, old_text):
    """Match ``old_text`` against ``concat`` ignoring fill-blank runs.

    Returns ``(start_pos_in_concat, actual_old_text_in_concat)`` or ``None``.

    A "fill-blank run" is 2+ consecutive characters drawn from the set
    ``[. … ․ ‥ · _]`` (possibly with whitespace inside the run). Both the
    document and the LLM-supplied old_text get those runs deleted before
    matching; positions in the stripped space are mapped back so the
    returned actual span covers exactly what the document stores
    (whitespace, fill-blanks and all).

    Single dots (sentence punctuation) are NOT stripped — only runs of 2+.

    Whitespace is also stripped, mirroring _find_whitespace_agnostic, so
    callers reaching this fallback don't need to call both.
    """

    norm_old = _normalize_for_match(old_text)
    norm_concat = _normalize_for_match(concat)

    def _mark_fillblanks(s: str):
        mark = [False] * len(s)
        for m in _FILLBLANK_RUN_RE.finditer(s):
            for i in range(m.start(), m.end()):
                mark[i] = True
        return mark

    concat_mark = _mark_fillblanks(norm_concat)
    old_mark = _mark_fillblanks(norm_old)

    stripped_concat_chars = []
    index_map = []
    for i, ch in enumerate(norm_concat):
        if concat_mark[i] or ch.isspace():
            continue
        stripped_concat_chars.append(ch)
        index_map.append(i)
    stripped_concat = "".join(stripped_concat_chars)

    stripped_old = "".join(
        ch for i, ch in enumerate(norm_old) if not old_mark[i] and not ch.isspace()
    )
    if not stripped_old:
        return None

    pos = stripped_concat.find(stripped_old)
    if pos < 0:
        pos = stripped_concat.lower().find(stripped_old.lower())
    if pos < 0:
        return None

    concat_start = index_map[pos]
    concat_end_char = index_map[pos + len(stripped_old) - 1]
    concat_end = concat_end_char + 1
    actual = concat[concat_start:concat_end]
    return (concat_start, actual)

def _dominant_rpr(runs, start_idx, end_idx, match_start, match_end):
    """Return the rPr of the run contributing the most characters to the match.

    When a match spans runs with different formatting (e.g. a short bold label
    run followed by a long non-bold body run), using the first run's rPr for
    the insertion causes the entire replacement to inherit the minority
    formatting.  Picking the *dominant* (most-characters) run's rPr avoids
    this: a 7-char bold "Number:" label loses to a 40-char non-bold body,
    so the insertion is correctly non-bold.
    """
    best_rpr = runs[start_idx]["rpr"]
    best_count = 0
    for i in range(start_idx, end_idx + 1):
        run = runs[i]
        seg_start = max(match_start, run["text_start"]) - run["text_start"]
        seg_end = min(match_end, run["text_end"]) - run["text_start"]
        count = seg_end - seg_start
        if count > best_count:
            best_count = count
            best_rpr = run["rpr"]
    return best_rpr

def _build_cross_run_change(xml_str, cross, new_text, author):
    """
    Build tracked change for text spanning multiple ``<w:r>`` elements.

    Each affected run contributes its own ``<w:r>`` with formatting inside
    the ``<w:del>`` block, so per-run formatting is preserved in the deletion.
    The insertion uses the formatting of the dominant (most-characters) run.

    If the runs are inside an existing ``<w:ins>`` block, the text is updated
    in-place (amending the insertion) without nested tracked changes.
    """
    runs = cross["runs"]
    start_idx = cross["start_idx"]
    end_idx = cross["end_idx"]
    match_start = cross["match_start"]
    match_end = cross["match_end"]
    actual_old = cross["actual_old"]

    start_run = runs[start_idx]
    end_run = runs[end_idx]

    prefix_offset = match_start - start_run["text_start"]
    prefix = start_run["decoded"][:prefix_offset]

    suffix_offset = match_end - end_run["text_start"]
    suffix = end_run["decoded"][suffix_offset:]

    replace_start = start_run["run_start"]
    replace_end = end_run["run_end"]

    inside_ins = _is_inside_ins(replace_start, xml_str)

    if inside_ins:

        parts = []
        if prefix:
            sp = _space_attr(prefix)
            parts.append(
                f"<w:r>{start_run['rpr']}<w:t{sp}>"
                f"{_xml_escape_text(prefix)}</w:t></w:r>"
            )
        if new_text:
            parts.append(_build_ins_runs(new_text, start_run['rpr']))
        if suffix:
            sp = _space_attr(suffix)
            parts.append(
                f"<w:r>{end_run['rpr']}<w:t{sp}>"
                f"{_xml_escape_text(suffix)}</w:t></w:r>"
            )
        replacement = "".join(parts)
        new_xml = xml_str[:replace_start] + replacement + xml_str[replace_end:]
        return new_xml, {
            "matched_text": actual_old,
            "replacement_text": new_text,
            "cross_run": True,
            "runs_affected": end_idx - start_idx + 1,
            "mode": "ins_amend",
        }

    next_id = _next_revision_id(xml_str)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts = []

    if prefix:
        sp = _space_attr(prefix)
        parts.append(
            f"<w:r>{start_run['rpr']}<w:t{sp}>"
            f"{_xml_escape_text(prefix)}</w:t></w:r>"
        )

    del_runs = []
    for i in range(start_idx, end_idx + 1):
        run = runs[i]
        del_start = max(match_start, run["text_start"]) - run["text_start"]
        del_end = min(match_end, run["text_end"]) - run["text_start"]
        del_text = run["decoded"][del_start:del_end]
        if del_text:
            sp = _space_attr(del_text)
            del_runs.append(
                f"<w:r>{run['rpr']}<w:delText{sp}>"
                f"{_xml_escape_text(del_text)}</w:delText></w:r>"
            )

    parts.append(
        f'<w:del w:id="{next_id}" w:author="{author}" w:date="{date_str}">'
        + "".join(del_runs)
        + "</w:del>"
    )

    if new_text:
        ins_rpr = _dominant_rpr(runs, start_idx, end_idx, match_start, match_end)
        parts.append(
            f'<w:ins w:id="{next_id + 1}" w:author="{author}" w:date="{date_str}">'
            + _build_ins_runs(new_text, ins_rpr)
            + "</w:ins>"
        )

    if suffix:
        sp = _space_attr(suffix)
        parts.append(
            f"<w:r>{end_run['rpr']}<w:t{sp}>"
            f"{_xml_escape_text(suffix)}</w:t></w:r>"
        )

    replacement = "".join(parts)
    new_xml = xml_str[:replace_start] + replacement + xml_str[replace_end:]

    return new_xml, {
        "matched_text": actual_old,
        "replacement_text": new_text,
        "cross_run": True,
        "runs_affected": end_idx - start_idx + 1,
        "revision_ids": [next_id] + ([next_id + 1] if new_text else []),
    }

def _scan_cross_paragraph(xml_str, t_re, tc_ranges, old_text):
    """
    Search for *old_text* spanning multiple ``<w:p>`` elements.

    Collects paragraph text, concatenates with separators, and attempts
    to locate *old_text* in the concatenated string.  Tries ``\\n\\n``,
    ``\\n``, and space as separators to account for how the LLM may
    collapse paragraph boundaries.

    Returns a candidate dict or ``None``.
    """
    p_re = re.compile(r"<w:p\b[^>]*>.*?</w:p>", re.DOTALL)

    paras = []
    for p_match in p_re.finditer(xml_str):
        p_xml = p_match.group(0)

        texts = []
        first_rpr = None
        t_br_re = re.compile(
            r"<w:t([^>]*)>([^<]*)</w:t>|<w:br\b[^/]*/>",
            re.DOTALL,
        )
        for m in t_br_re.finditer(p_xml):
            abs_pos = p_match.start() + m.start()
            if _in_tracked_change(abs_pos, tc_ranges):
                continue
            if m.group(2) is not None:
                decoded = _decode_xml_text(m.group(2))
                if decoded:
                    texts.append(decoded)
                    if first_rpr is None:
                        try:
                            rs, re_ = _find_enclosing_run(xml_str, abs_pos)
                            first_rpr = _extract_rpr_str(xml_str[rs:re_])
                        except ValueError:
                            pass
            else:

                texts.append("\n")

        para_text = "".join(texts)
        paras.append({
            "text": para_text,
            "p_start": p_match.start(),
            "p_end": p_match.end(),
            "ppr": _extract_ppr_str(p_xml),
            "rpr": first_rpr or "",
            "ctx": _structural_context(xml_str, p_match.start()),
        })

    if len(paras) < 2:
        return None

    norm_old = _normalize_for_match(old_text)

    for sep in ("\n\n", "\n", " "):
        concat = sep.join(p["text"] for p in paras)
        norm_concat = _normalize_for_match(concat)

        search_start = 0
        best_candidate = None

        while True:
            idx = norm_concat.find(norm_old, search_start)
            if idx == -1:
                idx = norm_concat.lower().find(norm_old.lower(), search_start)
            if idx < 0:
                break

            char_pos = 0
            start_para = end_para = None
            match_end = idx + len(norm_old)

            for i, p in enumerate(paras):
                p_len = len(_normalize_for_match(p["text"]))
                p_end_pos = char_pos + p_len

                if start_para is None and idx < p_end_pos:
                    start_para = i
                if match_end <= p_end_pos:
                    end_para = i
                    break

                char_pos = p_end_pos + len(sep)

            if start_para is not None and end_para is not None and start_para != end_para:

                ctxs = {paras[i]["ctx"] for i in range(start_para, end_para + 1)
                        if paras[i]["text"].strip()}
                if len(ctxs) > 1:
                    search_start = idx + 1
                    continue

                candidate = {
                    "paras": paras,
                    "start_para": start_para,
                    "end_para": end_para,
                    "actual_old": old_text,
                }

                all_ins = all(
                    _is_ins_only_paragraph(xml_str, paras[i]["p_start"], paras[i]["p_end"])
                    for i in range(start_para, end_para + 1)
                    if paras[i]["text"].strip()
                )

                if not all_ins:
                    return candidate                                         

                if best_candidate is None:
                    best_candidate = candidate
                search_start = idx + 1
            else:
                break

        if best_candidate is not None:
            return best_candidate

    return None

def _is_ins_only_paragraph(xml_str: str, p_start: int, p_end: int) -> bool:
    """Check if a paragraph's visible content is entirely inside ``<w:ins>`` blocks.

    Returns True when all ``<w:t>`` elements in the paragraph are enclosed by
    ``<w:ins>``.  In Word's track-changes model, deleting such text should
    simply *remove* the insertion (un-insert it), not create a ``<w:del>`` mark
    for text that was never in the original document.
    """
    p_xml = xml_str[p_start:p_end]
    t_re = re.compile(r"<w:t\b[^>]*>[^<]*</w:t>", re.DOTALL)
    ins_re = re.compile(r"<w:ins\b[^>]*>.*?</w:ins>", re.DOTALL)
    del_re_local = re.compile(r"<w:del\b[^>]*>.*?</w:del>", re.DOTALL)

    ins_ranges = [(m.start(), m.end()) for m in ins_re.finditer(p_xml)]
    del_ranges = [(m.start(), m.end()) for m in del_re_local.finditer(p_xml)]

    if not ins_ranges:
        return False

    found_visible_t = False
    for t_m in t_re.finditer(p_xml):
        t_pos = t_m.start()

        if any(s <= t_pos < e for s, e in del_ranges):
            continue
        found_visible_t = True

        if not any(s <= t_pos < e for s, e in ins_ranges):
            return False                                

    return found_visible_t

def _build_cross_paragraph_change(xml_str, cross, new_text, author):
    """
    Build tracked change for text spanning multiple ``<w:p>`` elements.

    DEL and INS are paired **in the same** ``<w:p>`` element whenever
    possible.  This is critical for heading-numbered documents: separate
    ``<w:p>`` elements each consume a heading number, leaving "blank"
    clause slots for the DEL paragraphs.  Placing DEL + INS in the same
    ``<w:p>`` makes them share one heading number, which is correct.

    Paragraphs whose visible content is entirely inside ``<w:ins>`` blocks
    (from a previous edit) are simply **dropped** instead of being wrapped
    in ``<w:del>``.  In Word's track-changes model, deleting a tracked
    insertion just removes it — it must not appear as a deletion of text
    that was never in the original document.

    Layout rules:
    - Paired (1:1): ``<w:p> pPr + DEL + INS </w:p>``
    - Extra DEL (more old than new): ``<w:p> pPr + DEL </w:p>``
    - Extra INS (more new than old): ``<w:p> pPr + INS </w:p>``
    - Ins-only paragraph (previous insertion): dropped entirely
    """
    paras = cross["paras"]
    start_idx = cross["start_para"]
    end_idx = cross["end_para"]
    actual_old = cross["actual_old"]

    replace_start = paras[start_idx]["p_start"]
    replace_end = paras[end_idx]["p_end"]

    matched = []
    for i in range(start_idx, end_idx + 1):
        p = paras[i]
        if not p["text"].strip():
            continue
        p["ins_only"] = _is_ins_only_paragraph(
            xml_str, p["p_start"], p["p_end"]
        )
        matched.append(p)

    real_matched = [p for p in matched if not p.get("ins_only")]
    ins_only_dropped = [p for p in matched if p.get("ins_only")]

    fallback_rpr = (real_matched[0]["rpr"] if real_matched
                    else matched[0]["rpr"] if matched else "")

    next_id = _next_revision_id(xml_str)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    result_parts = []
    id_counter = next_id

    new_lines = [l for l in new_text.split('\n') if l.strip()] if new_text else []
    n_del = len(real_matched)
    n_ins = len(new_lines)
    n_paired = min(n_del, n_ins)

    for i in range(n_paired):
        p = real_matched[i]
        line = new_lines[i]
        p_rpr = p["rpr"] or fallback_rpr
        sp_d = _space_attr(p["text"])

        result_parts.append(
            f"<w:p>{p['ppr']}"
            f'<w:del w:id="{id_counter}" w:author="{author}" w:date="{date_str}">'
            f"<w:r>{p_rpr}<w:delText{sp_d}>{_xml_escape_text(p['text'])}</w:delText></w:r>"
            f"</w:del>"
            f'<w:ins w:id="{id_counter + 1}" w:author="{author}" w:date="{date_str}">'
            + _build_ins_runs(line, p_rpr)
            + "</w:ins>"
            "</w:p>"
        )
        id_counter += 2

    for i in range(n_paired, n_del):
        p = real_matched[i]
        p_rpr = p["rpr"] or fallback_rpr
        sp = _space_attr(p["text"])
        result_parts.append(
            f"<w:p>{p['ppr']}"
            f'<w:del w:id="{id_counter}" w:author="{author}" w:date="{date_str}">'
            f"<w:r>{p_rpr}<w:delText{sp}>{_xml_escape_text(p['text'])}</w:delText></w:r>"
            f"</w:del>"
            f"</w:p>"
        )
        id_counter += 1

    for i in range(n_paired, n_ins):
        line = new_lines[i]
        src = (real_matched[min(i, n_del - 1)] if real_matched
               else matched[min(i, len(matched) - 1)] if matched
               else {"ppr": "", "rpr": ""})
        ppr = _strip_ppr_numbering(src["ppr"])
        rpr = _strip_rpr_bold(src["rpr"] or fallback_rpr)
        result_parts.append(
            f"<w:p>{ppr}"
            f'<w:ins w:id="{id_counter}" w:author="{author}" w:date="{date_str}">'
            + _build_ins_runs(line, rpr)
            + "</w:ins>"
            "</w:p>"
        )
        id_counter += 1

    replacement = "".join(result_parts)
    new_xml = xml_str[:replace_start] + replacement + xml_str[replace_end:]

    return new_xml, {
        "matched_text": actual_old,
        "replacement_text": new_text,
        "cross_paragraph": True,
        "paragraphs_matched": len(matched),
        "paragraphs_replaced": n_ins,
        "paragraphs_dropped": len(ins_only_dropped),
        "revision_ids": list(range(next_id, id_counter)),
    }

def _structural_context(xml_str: str, pos: int) -> tuple:
    """Return a structural nesting key for a position in the XML.

    Two paragraphs have the same context iff they are in the same table
    cell (or both at body level).  Uses both nesting depth AND cumulative
    ``</w:tc>`` close count to distinguish different cells at the same
    depth — plain depth counting gives identical tuples for adjacent cells.

    Cross-paragraph edits that span different contexts would cut across
    ``<w:tc>``/``<w:tr>``/``<w:tbl>`` wrappers, producing invalid XML.
    """
    prefix = xml_str[:pos]
    tbl = prefix.count("<w:tbl") - prefix.count("</w:tbl>")
    tr = prefix.count("<w:tr") - prefix.count("</w:tr>")
    tc = prefix.count("<w:tc") - prefix.count("</w:tc>")
    if tc > 0:

        tc_seq = prefix.count("</w:tc>")
        return (tbl, tr, tc, tc_seq)
    return (tbl, tr, tc)

def _decode_xml_text(raw: str) -> str:
    """Decode XML entities in ``<w:t>`` content to plain Unicode."""
    result = raw
    for entity, char in _XML_ENTITY_DECODE.items():
        result = result.replace(entity, char)

    result = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), result)
    result = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), result)
    return result

def _normalize_quotes(text: str) -> str:
    """Collapse smart/curly quotes to ASCII for comparison."""
    return (
        text
        .replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
    )

def _normalize_symbols(text: str) -> str:
    """Normalise confusable bullet/dash/ellipsis characters for comparison.

    LLMs often substitute visually-similar Unicode symbols when reproducing
    document text (e.g. ● U+25CF ↔ • U+2022).  Mapping them to a single
    canonical form prevents spurious match failures.
    """
    return (
        text

        .replace("\u25cf", "\u2022")                              
        .replace("\u25cb", "\u25e6")                                    
        .replace("\u25a0", "\u25aa")                                          

        .replace("\u2014", "\u2013")                          
        .replace("\u2012", "\u2013")                              

        .replace("\u2026", "...")                                    
    )

def _normalize_whitespace(text: str) -> str:
    """Normalise non-breaking spaces and other Unicode whitespace to ASCII space."""

    return re.sub(r"[\xa0\u2002\u2003\u2009\u200a\u202f]", " ", text)

def _xml_escape_text(text: str) -> str:
    """Escape plain text for XML element content, re-escaping smart quotes."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char, entity in SMART_QUOTE_REPLACEMENTS.items():
        text = text.replace(char, entity)
    return text

def _space_attr(text: str) -> str:
    """Return ``xml:space='preserve'`` attr string if *text* has edge whitespace."""
    if text and (text[0] in " \t" or text[-1] in " \t"):
        return ' xml:space="preserve"'
    return ""

_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

def _parse_md_bold(text: str) -> list:
    """Parse ``**bold**`` markers in *text* into segments.

    Returns a list of ``(segment_text, is_bold)`` tuples.
    Only matches double-asterisk (``**``).  Single ``*`` is literal.

    Fast-path: if no ``**`` is present, returns a single non-bold segment.
    """
    if "**" not in text:
        return [(text, False)]

    segments = []
    last_end = 0
    for m in _MD_BOLD_RE.finditer(text):

        if m.start() > last_end:
            segments.append((text[last_end:m.start()], False))

        segments.append((m.group(1), True))
        last_end = m.end()

    if last_end < len(text):
        segments.append((text[last_end:], False))

    return [(t, b) for t, b in segments if t]

def _modify_rpr_bold(rpr_str: str, bold: bool) -> str:
    """Return *rpr_str* with ``<w:b/>`` added when *bold* is True.

    Handles:
    - Empty string → ``<w:rPr><w:b/></w:rPr>``
    - Self-closing ``<w:rPr/>`` → ``<w:rPr><w:b/></w:rPr>``
    - Already has ``<w:b/>`` → no change
    - Has ``<w:b w:val="0"/>`` (explicit off) → replaced with ``<w:b/>``
    - Non-bold segment → returns *rpr_str* unchanged
    """
    if not bold:
        return rpr_str

    if re.search(r"<w:b\s*/>", rpr_str) or re.search(r'<w:b\s+w:val="1"\s*/>', rpr_str):
        return rpr_str

    result = re.sub(r'<w:b\s+w:val="0"\s*/>', "", rpr_str)

    if not result:
        return "<w:rPr><w:b/></w:rPr>"
    if re.match(r"<w:rPr\s*/>", result):
        return "<w:rPr><w:b/></w:rPr>"
    if "<w:rPr" in result:
        return re.sub(r"(<w:rPr\b[^>]*>)", r"\1<w:b/>", result, count=1)
    return "<w:rPr><w:b/></w:rPr>"

def _strip_rpr_bold(rpr_str: str) -> str:
    """Remove ``<w:b/>`` and ``<w:b w:val="1"/>`` from an rPr XML string.

    Used for multi-paragraph insertions where additional lines should not
    inherit bold formatting from the original matched heading/run.
    """
    if not rpr_str:
        return rpr_str
    result = re.sub(r'<w:b\s*/>', '', rpr_str)
    result = re.sub(r'<w:b\s+w:val="1"\s*/>', '', result)
    return result

def _strip_ppr_numbering(ppr_str: str) -> str:
    """Remove ``<w:numPr>...</w:numPr>`` from a pPr XML string.

    Used for multi-paragraph insertions where additional lines should not
    inherit the heading-level numbering from the original matched paragraph.
    """
    if not ppr_str:
        return ppr_str
    return re.sub(r'<w:numPr>.*?</w:numPr>', '', ppr_str, flags=re.DOTALL)

def _build_ins_runs(text: str, base_rpr: str) -> str:
    """Generate ``<w:r>`` elements from *text*, translating ``**bold**`` markers.

    If *text* contains ``**bold**`` markers, multiple ``<w:r>`` elements are
    generated — bold segments get ``<w:b/>`` injected into *base_rpr*.
    If no markdown is present, a single ``<w:r>`` is returned (identical
    to the previous behaviour).
    """
    segments = _parse_md_bold(text)

    if len(segments) == 1 and not segments[0][1]:

        sp = _space_attr(text)
        return f"<w:r>{base_rpr}<w:t{sp}>{_xml_escape_text(text)}</w:t></w:r>"

    runs = []
    for seg_text, is_bold in segments:
        rpr = _modify_rpr_bold(base_rpr, is_bold)
        sp = _space_attr(seg_text)
        runs.append(
            f"<w:r>{rpr}<w:t{sp}>{_xml_escape_text(seg_text)}</w:t></w:r>"
        )
    return "".join(runs)

def _tracked_change_ranges(xml_str: str) -> list:
    """Return ``[(start, end), ...]`` for ``<w:del>`` blocks only.

    Text inside ``<w:ins>`` IS current document content and must remain
    matchable so that subsequent edits can modify previously-inserted text.
    Only ``<w:del>`` (already-deleted text) should be skipped during matching.
    """
    ranges = []
    for m in re.finditer(r"<w:del\b[^>]*>.*?</w:del>", xml_str, re.DOTALL):
        ranges.append((m.start(), m.end()))
    return ranges

def _in_tracked_change(pos: int, ranges: list) -> bool:
    return any(s <= pos < e for s, e in ranges)

def _is_inside_del_dom(node) -> bool:
    """Check whether a DOM *node* is inside a ``<w:del>`` ancestor."""
    parent = node.parentNode
    while parent:
        name = getattr(parent, "localName", None) or getattr(parent, "tagName", "")
        if name == "del" or name.endswith(":del"):
            return True
        parent = parent.parentNode
    return False

def _is_inside_ins(pos: int, xml_str: str) -> bool:
    """Check whether *pos* falls inside a ``<w:ins>`` block."""
    for m in re.finditer(r"<w:ins\b[^>]*>.*?</w:ins>", xml_str, re.DOTALL):
        if m.start() <= pos < m.end():
            return True
    return False

def _toc_paragraph_ranges(xml_str: str) -> list:
    """Return ``[(start, end), ...]`` for all Table of Contents regions.

    Detects two OOXML patterns:

    A. Structured Document Tags (``<w:sdt>``) containing
       ``<w:docPartGallery w:val="Table of Contents"/>``.
       The entire SDT block is marked as a skip zone.

    B. Standalone paragraphs styled ``TOC1``, ``TOC2``, etc.
       (outside any SDT block already captured by pattern A).

    These ranges are merged with ``<w:del>`` ranges in :func:`_skip_ranges`
    so that all five scanning passes in :func:`apply_text_edit` automatically
    skip TOC content.  This prevents false matches when heading text appears
    in both the TOC and the document body.
    """
    ranges = []
    seen_spans = set()

    for m in re.finditer(r"<w:sdt\b[^>]*>.*?</w:sdt>", xml_str, re.DOTALL):
        sdt_xml = m.group(0)
        if "docPartGallery" in sdt_xml and "Table of Contents" in sdt_xml:
            span = (m.start(), m.end())
            ranges.append(span)
            seen_spans.add(span)

    for m in re.finditer(r"<w:p\b[^>]*>.*?</w:p>", xml_str, re.DOTALL):
        if not re.search(r'<w:pStyle[^>]*w:val="TOC\d+"', m.group(0)):
            continue
        span = (m.start(), m.end())

        if any(s <= span[0] and span[1] <= e for s, e in ranges):
            continue
        ranges.append(span)

    return ranges

def _skip_ranges(xml_str: str) -> list:
    """Return merged skip zones: ``<w:del>`` blocks + TOC regions.

    Combines :func:`_tracked_change_ranges` (deleted text) with
    :func:`_toc_paragraph_ranges` (auto-generated TOC) into a sorted,
    non-overlapping list of ``(start, end)`` ranges.

    All five scanning passes in :func:`apply_text_edit` use this to avoid
    matching text in deleted blocks or TOC paragraphs.
    """
    raw = _tracked_change_ranges(xml_str) + _toc_paragraph_ranges(xml_str)
    if not raw:
        return []

    raw.sort()
    merged = [raw[0]]
    for s, e in raw[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged

def _find_text_position(xml_str: str, text: str) -> int | None:
    """Find the byte position of *text* in ``<w:t>`` elements (for proximity)."""
    t_re = re.compile(r"<w:t[^>]*>([^<]*)</w:t>", re.DOTALL)
    text_lower = text.lower()
    for m in t_re.finditer(xml_str):
        if text_lower in _decode_xml_text(m.group(1)).lower():
            return m.start()
    return None

def _resolve_candidates(xml_str: str, candidates: list, near_text: str, pos_key: str):
    """
    Pick one candidate from *candidates*.

    - 1 candidate → return it directly.
    - >1 + *near_text* → pick the one closest to *near_text* in the XML.
    - >1 + no hint → return ``None`` (ambiguous).
    """
    if len(candidates) <= 1:
        return candidates[0] if candidates else None
    if not near_text:
        return None
    near_pos = _find_text_position(xml_str, near_text)
    if near_pos is None:
        return None

    def _pos(c):
        p = c.get(pos_key)
        return p[0] if isinstance(p, tuple) else p

    return min(candidates, key=lambda c: abs(_pos(c) - near_pos))

def _ambiguity_error(old_text: str, count: int) -> dict:
    """Build error dict when *old_text* matches multiple locations."""
    return {
        "error": (
            f"Text '{old_text[:80]}' matches {count} locations in the document. "
            "Include more surrounding text in old_text to make it unique, "
            "or add near_text with text from a nearby heading or the same row."
        ),
        "suggestion": (
            f"Found {count} identical matches (likely same value in different table cells). "
            "Use near_text parameter with text from the same row to disambiguate. "
            "Example: near_text='Dubai governing law' to target that specific row."
        ),
        "match_count": count,
    }

def _scan_for_match(xml_str, t_re, tc_ranges, old_text, mode):
    """
    Scan all ``<w:t>`` elements for *old_text* using the given *mode*.

    Returns a **list** of candidate dicts (empty if no matches).
    """
    norm_old = _normalize_for_match(old_text) if mode == "quotes" else None
    lower_old = _normalize_for_match(old_text.lower()) if mode == "icase" else None

    candidates = []

    for m in t_re.finditer(xml_str):

        if _in_tracked_change(m.start(), tc_ranges):
            continue

        raw_content = m.group(2)
        decoded = _decode_xml_text(raw_content)

        if mode == "exact":
            if old_text not in decoded:
                continue
            offset = decoded.index(old_text)
            actual_old = old_text
        elif mode == "quotes":
            norm_decoded = _normalize_for_match(decoded)
            if norm_old not in norm_decoded:
                continue
            offset = norm_decoded.index(norm_old)
            actual_old = decoded[offset : offset + len(old_text)]
        elif mode == "icase":
            norm_decoded = _normalize_for_match(decoded.lower())
            if lower_old not in norm_decoded:
                continue
            offset = norm_decoded.index(lower_old)
            actual_old = decoded[offset : offset + len(old_text)]
        else:
            continue

        try:
            run_start, run_end = _find_enclosing_run(xml_str, m.start())
        except ValueError:
            continue

        candidates.append({
            "actual_old": actual_old,
            "prefix": decoded[:offset],
            "suffix": decoded[offset + len(old_text) :],
            "run_span": (run_start, run_end),
        })

    return candidates

def _find_enclosing_run(xml_str: str, inner_pos: int) -> tuple:
    """
    Return ``(start, end)`` byte offsets of the ``<w:r>...</w:r>`` element
    enclosing *inner_pos*.
    """
    pos = inner_pos
    while pos >= 0:
        pos = xml_str.rfind("<w:r", 0, pos)
        if pos == -1:
            raise ValueError("No enclosing <w:r> found")

        char_after = xml_str[pos + 4 : pos + 5]
        if char_after in (">", " ", "\n", "\r", "\t"):

            if "</w:r>" not in xml_str[pos:inner_pos]:
                break

    end = xml_str.find("</w:r>", inner_pos)
    if end == -1:
        raise ValueError("No closing </w:r> found")
    end += len("</w:r>")
    return pos, end

def _extract_rpr_str(run_xml: str) -> str:
    """Extract ``<w:rPr>...</w:rPr>`` from a serialised ``<w:r>`` string."""

    m = re.search(r"<w:rPr\b[^>]*/>|<w:rPr\b[^>]*>.*?</w:rPr>", run_xml, re.DOTALL)
    return m.group(0) if m else ""

def _find_enclosing_paragraph(xml_str: str, inner_pos: int) -> tuple:
    """Return ``(start, end)`` of the ``<w:p>...</w:p>`` enclosing *inner_pos*."""
    pos = inner_pos
    while pos >= 0:
        pos = xml_str.rfind("<w:p", 0, pos)
        if pos == -1:
            raise ValueError("No enclosing <w:p> found")
        char_after = xml_str[pos + 4 : pos + 5]
        if char_after in (">", " ", "\n", "\r", "\t"):

            if "</w:p>" not in xml_str[pos:inner_pos]:
                break
    end = xml_str.find("</w:p>", inner_pos)
    if end == -1:
        raise ValueError("No closing </w:p> found")
    end += len("</w:p>")
    return pos, end

def _extract_ppr_str(para_xml: str) -> str:
    """Extract ``<w:pPr>...</w:pPr>`` from a serialised ``<w:p>`` string."""
    m = re.search(r"<w:pPr\b[^>]*/>|<w:pPr\b[^>]*>.*?</w:pPr>", para_xml, re.DOTALL)
    return m.group(0) if m else ""

def _next_revision_id(xml_str: str) -> int:
    """Return the next available ``w:id`` value (max existing + 1)."""
    ids = [int(x) for x in re.findall(r'w:id="(\d+)"', xml_str)]
    return max(ids, default=1000) + 1

def _nearby_paragraph_text(xml_str: str, search_text: str) -> str:
    """Find the 3 most similar paragraph texts using fuzzy matching.

    Returns a pipe-separated string of ``[similarity%] text`` entries so the
    LLM can see what's actually in the document and self-correct.
    """
    from difflib import SequenceMatcher

    p_re = re.compile(r"<w:p\b[^>]*>(.*?)</w:p>", re.DOTALL)
    t_re = re.compile(r"<w:t[^>]*>([^<]*)</w:t>", re.DOTALL)
    search_lower = search_text.lower()
    candidates: list = []

    for pm in p_re.finditer(xml_str):
        p_text = " ".join(
            _decode_xml_text(tm.group(1)) for tm in t_re.finditer(pm.group(1))
        )
        p_text = p_text.strip()
        if not p_text:
            continue
        ratio = SequenceMatcher(None, search_lower, p_text.lower()).ratio()
        candidates.append((ratio, p_text[:200]))

    candidates.sort(key=lambda x: -x[0])
    top = candidates[:3]
    if top and top[0][0] > 0.3:
        return " | ".join(f"[{r:.0%}] {t}" for r, t in top)
    return ""

def _is_inside_del_str(container_xml: str, pos: int) -> bool:
    """Check if *pos* is inside a ``<w:del>`` block (string-based).

    Uses ``"<w:del "`` (with trailing space) to avoid false positives from
    ``<w:delText>`` which also starts with ``<w:del``.
    """
    prefix = container_xml[:pos]
    return prefix.count("<w:del ") > prefix.count("</w:del>")

def _extract_row_text(xml_str: str, pos: int) -> str:
    """Extract table row text as ``| cell1 | cell2 |`` around *pos*."""
    tr_start = xml_str.rfind("<w:tr", 0, pos)
    if tr_start == -1:
        return ""
    tr_end = xml_str.find("</w:tr>", pos)
    if tr_end == -1:
        return ""
    tr_xml = xml_str[tr_start : tr_end + len("</w:tr>")]

    t_re = re.compile(r"<w:t[^>]*>([^<]*)</w:t>", re.DOTALL)
    tc_re = re.compile(r"<w:tc\b[^>]*>(.*?)</w:tc>", re.DOTALL)
    cells = []
    for tc_m in tc_re.finditer(tr_xml):
        tc_body = tc_m.group(1)
        cell_text = " ".join(
            _decode_xml_text(t.group(1))
            for t in t_re.finditer(tc_body)
            if not _is_inside_del_str(tc_body, t.start())
        ).strip()
        cells.append(cell_text)
    if cells:
        return "| " + " | ".join(cells) + " |"
    return ""

def _extract_para_context(xml_str: str, pos: int) -> str:
    """Extract the edited paragraph (``>>>``) + preceding paragraph."""
    t_re = re.compile(r"<w:t[^>]*>([^<]*)</w:t>", re.DOTALL)
    p_re = re.compile(r"<w:p\b[^>]*>(.*?)</w:p>", re.DOTALL)

    prev_text = ""
    for p_m in p_re.finditer(xml_str):
        p_body = p_m.group(1)
        p_text = " ".join(
            _decode_xml_text(t.group(1))
            for t in t_re.finditer(p_body)
            if not _is_inside_del_str(p_body, t.start())
        ).strip()
        if p_m.start() <= pos <= p_m.end():
            parts = []
            if prev_text:
                parts.append(f"...{prev_text[-80:]}")
            parts.append(f">>> {p_text[:200]}")
            return "\n".join(parts)
        if p_text:
            prev_text = p_text
    return ""

def _context_around_revision(xml_str: str, revision_ids: list) -> str:
    """Extract surrounding text near the first tracked change for verification.

    Returns pipe-delimited row text for table edits, or ``>>> paragraph``
    for body edits.  Best-effort — returns ``""`` on any failure.
    """
    if not revision_ids:
        return ""
    first_id = str(revision_ids[0])
    for pat in (f'w:id="{first_id}"', f"w:id='{first_id}'"):
        edit_pos = xml_str.find(pat)
        if edit_pos != -1:
            break
    else:
        return ""

    prefix = xml_str[:edit_pos]
    in_cell = prefix.count("<w:tc") > prefix.count("</w:tc>")

    if in_cell:
        return _extract_row_text(xml_str, edit_pos)
    return _extract_para_context(xml_str, edit_pos)

_MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024                                 

def _read_zip_entry(blob: bytes, entry_path: str) -> bytes:
    """Read a single file from a ZIP blob with zip-bomb protection."""
    with zipfile.ZipFile(io.BytesIO(blob), "r") as zf:
        info = zf.getinfo(entry_path)
        if info.file_size > _MAX_UNCOMPRESSED_SIZE:
            raise ValueError(
                f"ZIP entry '{entry_path}' uncompressed size "
                f"({info.file_size:,} bytes) exceeds limit"
            )

        if info.compress_size > 0 and info.file_size / info.compress_size > 100:
            raise ValueError(
                f"ZIP entry '{entry_path}' has suspicious compression ratio "
                f"({info.file_size / info.compress_size:.0f}:1)"
            )
        return zf.read(entry_path)

def _condense_xml(xml_str: str) -> str:
    """
    Remove pretty-print whitespace between XML elements for compact storage.
    Preserves whitespace inside ``<w:t>`` and ``<w:delText>`` elements.
    """
    try:
        dom = safe_parseString(xml_str.encode("utf-8"))

        _strip_whitespace_nodes(dom.documentElement)
        return dom.toxml(encoding="UTF-8").decode("utf-8")
    except Exception:

        return xml_str

def _strip_whitespace_nodes(element):
    """Remove whitespace-only text nodes, except inside w:t / w:delText."""
    TEXT_TAGS = {"t", "delText", "instrText", "delInstrText"}

    for child in list(element.childNodes):
        if child.nodeType == child.ELEMENT_NODE:
            name = child.localName or child.tagName
            tag = name.split(":")[-1] if ":" in name else name
            if tag not in TEXT_TAGS:
                _strip_whitespace_nodes(child)
        elif child.nodeType == child.TEXT_NODE:

            parent_name = element.localName or element.tagName
            parent_tag = parent_name.split(":")[-1] if ":" in parent_name else parent_name
            if parent_tag not in TEXT_TAGS:
                if child.nodeValue and child.nodeValue.strip() == "":
                    element.removeChild(child)

def _find_elements(root, tag: str) -> list:
    """Find all elements matching *tag* (namespace-agnostic)."""
    results = []

    def traverse(node):
        if node.nodeType == node.ELEMENT_NODE:
            name = node.localName or node.tagName
            if name == tag or name.endswith(f":{tag}"):
                results.append(node)
            for child in node.childNodes:
                traverse(child)

    traverse(root)
    return results

def _get_child(parent, tag: str):
    """Get first direct child element matching *tag*."""
    for child in parent.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            name = child.localName or child.tagName
            if name == tag or name.endswith(f":{tag}"):
                return child
    return None

def _get_children(parent, tag: str) -> list:
    """Get all direct child elements matching *tag*."""
    results = []
    for child in parent.childNodes:
        if child.nodeType == child.ELEMENT_NODE:
            name = child.localName or child.tagName
            if name == tag or name.endswith(f":{tag}"):
                results.append(child)
    return results

def _get_text_content(element) -> str:
    """Get the text content of an element (direct text node children)."""
    parts = []
    for child in element.childNodes:
        if child.nodeType == child.TEXT_NODE:
            parts.append(child.nodeValue or "")
    return "".join(parts)

def _remove_elements(root, tag: str):
    """Remove all elements matching *tag* from the tree."""
    for elem in _find_elements(root, tag):
        if elem.parentNode:
            elem.parentNode.removeChild(elem)

def _strip_run_rsid_attrs(root):
    """Strip rsid* attributes from <w:r> and <w:rPr> elements (revision noise).

    rsid attributes on <w:rPr> block run merging in _can_merge() because it
    compares rPr.toxml().  Stripping them before merging lets visually-identical
    runs merge correctly.
    """
    for run in _find_elements(root, "r"):
        for attr in list(run.attributes.values()):
            if "rsid" in attr.name.lower():
                run.removeAttribute(attr.name)

        rpr = _get_child(run, "rPr")
        if rpr is not None:
            for attr in list(rpr.attributes.values()):
                if "rsid" in attr.name.lower():
                    rpr.removeAttribute(attr.name)

def _is_run(node) -> bool:
    name = node.localName or node.tagName
    return name == "r" or name.endswith(":r")

def _is_adjacent(elem1, elem2) -> bool:
    """Check if two elements are adjacent (no elements between them)."""
    node = elem1.nextSibling
    while node:
        if node == elem2:
            return True
        if node.nodeType == node.ELEMENT_NODE:
            return False
        if node.nodeType == node.TEXT_NODE and node.data.strip():
            return False
        node = node.nextSibling
    return False

def _can_merge(run1, run2) -> bool:
    """Check if two runs have identical formatting (rPr)."""
    rpr1 = _get_child(run1, "rPr")
    rpr2 = _get_child(run2, "rPr")
    if (rpr1 is None) != (rpr2 is None):
        return False
    if rpr1 is None:
        return True
    return rpr1.toxml() == rpr2.toxml()

def _next_element_sibling(node):
    sibling = node.nextSibling
    while sibling:
        if sibling.nodeType == sibling.ELEMENT_NODE:
            return sibling
        sibling = sibling.nextSibling
    return None

def _next_sibling_run(node):
    sibling = node.nextSibling
    while sibling:
        if sibling.nodeType == sibling.ELEMENT_NODE:
            if _is_run(sibling):
                return sibling
        sibling = sibling.nextSibling
    return None

def _first_child_run(container):
    for child in container.childNodes:
        if child.nodeType == child.ELEMENT_NODE and _is_run(child):
            return child
    return None

def _merge_run_content(target, source):
    """Move content from *source* run into *target* (skip rPr)."""
    for child in list(source.childNodes):
        if child.nodeType == child.ELEMENT_NODE:
            name = child.localName or child.tagName
            if name != "rPr" and not name.endswith(":rPr"):
                target.appendChild(child)

def _consolidate_text(run):
    """Merge adjacent <w:t> elements inside a run into one."""
    t_elements = _get_children(run, "t")

    for i in range(len(t_elements) - 1, 0, -1):
        curr, prev = t_elements[i], t_elements[i - 1]

        if _is_adjacent(prev, curr):
            prev_text = prev.firstChild.data if prev.firstChild else ""
            curr_text = curr.firstChild.data if curr.firstChild else ""
            merged = prev_text + curr_text

            if prev.firstChild:
                prev.firstChild.data = merged
            else:
                prev.appendChild(run.ownerDocument.createTextNode(merged))

            if merged.startswith(" ") or merged.endswith(" "):
                prev.setAttribute("xml:space", "preserve")
            elif prev.hasAttribute("xml:space"):
                prev.removeAttribute("xml:space")

            run.removeChild(curr)

def _merge_runs_in(container) -> int:
    """Merge adjacent runs with identical formatting in a container."""
    merge_count = 0
    run = _first_child_run(container)

    while run:
        while True:
            next_elem = _next_element_sibling(run)
            if next_elem and _is_run(next_elem) and _can_merge(run, next_elem):
                _merge_run_content(run, next_elem)
                container.removeChild(next_elem)
                merge_count += 1
            else:
                break

        _consolidate_text(run)
        run = _next_sibling_run(run)

    return merge_count
