"""
Standalone Diff Tool for Document Comparison

Copyright 2026 AnyLegal

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

This module provides text comparison and redline rendering capabilities
suitable for legal document review. It uses diff-match-patch when available,
with a difflib fallback for environments where the dependency isn't installed.

Usage:
    from diff_tool import compute_diff, render_html_redline, render_plaintext_redline

    # Compute raw diff
    chunks = compute_diff(original_text, modified_text)

    # Render as HTML
    html = render_html_redline(original_text, modified_text)

    # Render as plaintext with markers
    plain = render_plaintext_redline(original_text, modified_text)
"""

import re
from typing import List, Tuple, Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    from diff_match_patch import diff_match_patch
    _DMP_AVAILABLE = True
except ImportError:
    import difflib
    _DMP_AVAILABLE = False

class DiffOperation(Enum):
    """Types of diff operations."""
    EQUAL = 0
    INSERT = 1
    DELETE = -1

@dataclass
class DiffChunk:
    """A chunk in a diff result."""
    operation: DiffOperation
    text: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "operation": self.operation.name.lower(),
            "text": self.text
        }

def compute_diff(text1: str, text2: str, word_level: bool = False) -> List[DiffChunk]:
    """
    Compute the differences between two texts.

    Args:
        text1: Original text
        text2: Modified text
        word_level: If True, diff at word boundaries (more readable for prose)

    Returns:
        List of DiffChunk objects representing the differences

    Example:
        >>> chunks = compute_diff("Hello world", "Hello there")
        >>> for c in chunks:
        ...     print(f"{c.operation.name}: '{c.text}'")
        EQUAL: 'Hello '
        DELETE: 'world'
        INSERT: 'there'
    """
    if word_level:
        return _compute_word_diff(text1, text2)

    if _DMP_AVAILABLE:
        return _compute_diff_dmp(text1, text2)
    else:
        return _compute_diff_difflib(text1, text2)

def _compute_diff_dmp(text1: str, text2: str) -> List[DiffChunk]:
    """Compute diff using diff-match-patch."""
    dmp = diff_match_patch()
    dmp.Diff_Timeout = 5.0
    dmp.Match_Threshold = 0.5
    dmp.Match_Distance = 1000

    diffs = dmp.diff_main(text1, text2)
    dmp.diff_cleanupSemantic(diffs)

    result = []
    for op, text in diffs:
        if op == 0:
            result.append(DiffChunk(DiffOperation.EQUAL, text))
        elif op == 1:
            result.append(DiffChunk(DiffOperation.INSERT, text))
        elif op == -1:
            result.append(DiffChunk(DiffOperation.DELETE, text))

    return result

def _compute_diff_difflib(text1: str, text2: str) -> List[DiffChunk]:
    """Compute diff using difflib (fallback)."""
    import difflib
    matcher = difflib.SequenceMatcher(None, text1, text2)
    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append(DiffChunk(DiffOperation.EQUAL, text1[i1:i2]))
        elif tag == 'replace':
            result.append(DiffChunk(DiffOperation.DELETE, text1[i1:i2]))
            result.append(DiffChunk(DiffOperation.INSERT, text2[j1:j2]))
        elif tag == 'delete':
            result.append(DiffChunk(DiffOperation.DELETE, text1[i1:i2]))
        elif tag == 'insert':
            result.append(DiffChunk(DiffOperation.INSERT, text2[j1:j2]))

    return result

def _compute_word_diff(text1: str, text2: str) -> List[DiffChunk]:
    """Compute word-level diff (better for legal text)."""
    def tokenize(text: str) -> List[str]:
        return re.findall(r'\S+|\s+', text)

    words1 = tokenize(text1)
    words2 = tokenize(text2)

    import difflib
    matcher = difflib.SequenceMatcher(None, words1, words2)
    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            result.append(DiffChunk(DiffOperation.EQUAL, ''.join(words1[i1:i2])))
        elif tag == 'replace':
            result.append(DiffChunk(DiffOperation.DELETE, ''.join(words1[i1:i2])))
            result.append(DiffChunk(DiffOperation.INSERT, ''.join(words2[j1:j2])))
        elif tag == 'delete':
            result.append(DiffChunk(DiffOperation.DELETE, ''.join(words1[i1:i2])))
        elif tag == 'insert':
            result.append(DiffChunk(DiffOperation.INSERT, ''.join(words2[j1:j2])))

    return result

def _escape_html(text: str) -> str:
    """Escape HTML entities."""
    return (
        text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )

def render_html_redline(
    text1: str,
    text2: str,
    delete_class: str = "redline-delete",
    insert_class: str = "redline-insert",
    word_level: bool = False
) -> str:
    """
    Render differences as HTML with CSS classes.

    Args:
        text1: Original text
        text2: Modified text
        delete_class: CSS class for deleted text
        insert_class: CSS class for inserted text
        word_level: If True, diff at word boundaries

    Returns:
        HTML string with redline markup

    Example:
        >>> html = render_html_redline("Hello world", "Hello there")
        >>> print(html)
        Hello <span class="redline-delete">world</span><span class="redline-insert">there</span>
    """
    diffs = compute_diff(text1, text2, word_level=word_level)

    html_parts = []
    for chunk in diffs:
        text = _escape_html(chunk.text)

        if chunk.operation == DiffOperation.EQUAL:
            html_parts.append(text)
        elif chunk.operation == DiffOperation.DELETE:
            html_parts.append(f'<span class="{delete_class}">{text}</span>')
        elif chunk.operation == DiffOperation.INSERT:
            html_parts.append(f'<span class="{insert_class}">{text}</span>')

    return ''.join(html_parts)

def render_word_compatible(text1: str, text2: str, word_level: bool = False) -> str:
    """
    Render differences in Word-compatible format.

    Uses inline styles that map to Word's track changes appearance:
    - Deletions: strikethrough in red
    - Insertions: underline in blue

    Args:
        text1: Original text
        text2: Modified text
        word_level: If True, diff at word boundaries

    Returns:
        HTML string that can be pasted into Word
    """
    diffs = compute_diff(text1, text2, word_level=word_level)

    html_parts = []
    for chunk in diffs:
        text = _escape_html(chunk.text)

        if chunk.operation == DiffOperation.EQUAL:
            html_parts.append(text)
        elif chunk.operation == DiffOperation.DELETE:
            html_parts.append(
                f'<span style="text-decoration: line-through; color: red;">{text}</span>'
            )
        elif chunk.operation == DiffOperation.INSERT:
            html_parts.append(
                f'<span style="text-decoration: underline; color: blue;">{text}</span>'
            )

    return ''.join(html_parts)

def render_plaintext_redline(
    text1: str,
    text2: str,
    delete_markers: Tuple[str, str] = ('[-', '-]'),
    insert_markers: Tuple[str, str] = ('{+', '+}'),
    word_level: bool = False
) -> str:
    """
    Render differences as plaintext with markers.

    Args:
        text1: Original text
        text2: Modified text
        delete_markers: Tuple of (start, end) markers for deletions
        insert_markers: Tuple of (start, end) markers for insertions
        word_level: If True, diff at word boundaries

    Returns:
        Plain text with redline markers

    Example:
        >>> plain = render_plaintext_redline("Hello world", "Hello there")
        >>> print(plain)
        Hello [-world-]{+there+}
    """
    diffs = compute_diff(text1, text2, word_level=word_level)

    parts = []
    for chunk in diffs:
        if chunk.operation == DiffOperation.EQUAL:
            parts.append(chunk.text)
        elif chunk.operation == DiffOperation.DELETE:
            parts.append(f'{delete_markers[0]}{chunk.text}{delete_markers[1]}')
        elif chunk.operation == DiffOperation.INSERT:
            parts.append(f'{insert_markers[0]}{chunk.text}{insert_markers[1]}')

    return ''.join(parts)

def get_change_summary(text1: str, text2: str) -> Dict[str, Any]:
    """
    Get a summary of changes between two texts.

    Args:
        text1: Original text
        text2: Modified text

    Returns:
        Dict with:
        - insertions: number of insertion chunks
        - deletions: number of deletion chunks
        - unchanged_chunks: number of unchanged chunks
        - inserted_chars: total characters inserted
        - deleted_chars: total characters deleted
        - net_change: net character change (inserted - deleted)
    """
    diffs = compute_diff(text1, text2)

    insertions = 0
    deletions = 0
    unchanged = 0
    inserted_chars = 0
    deleted_chars = 0

    for chunk in diffs:
        if chunk.operation == DiffOperation.EQUAL:
            unchanged += 1
        elif chunk.operation == DiffOperation.INSERT:
            insertions += 1
            inserted_chars += len(chunk.text)
        elif chunk.operation == DiffOperation.DELETE:
            deletions += 1
            deleted_chars += len(chunk.text)

    return {
        "insertions": insertions,
        "deletions": deletions,
        "unchanged_chunks": unchanged,
        "inserted_chars": inserted_chars,
        "deleted_chars": deleted_chars,
        "net_change": inserted_chars - deleted_chars,
        "has_changes": insertions > 0 or deletions > 0
    }

def compute_similarity(text1: str, text2: str) -> float:
    """
    Compute similarity ratio between two texts.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    if not text1 and not text2:
        return 1.0
    if not text1 or not text2:
        return 0.0

    from difflib import SequenceMatcher
    return SequenceMatcher(None, text1, text2).ratio()

def apply_changes(original: str, changes: List[Dict[str, str]]) -> str:
    """
    Apply a list of changes to the original text.

    Args:
        original: Original text
        changes: List of change dicts, each with:
            - 'original': Text to find and replace
            - 'suggested': Replacement text

    Returns:
        Text with all changes applied

    Example:
        >>> result = apply_changes("Hello world", [{"original": "world", "suggested": "there"}])
        >>> print(result)
        Hello there
    """
    result = original

    for change in changes:
        old_text = change.get('original', '')
        new_text = change.get('suggested', '')

        if old_text and new_text:
            result = result.replace(old_text, new_text, 1)

    return result

def generate_redline_tool(original: str, revised: str) -> Dict[str, Any]:
    """
    Tool interface for generating redlines.

    Designed for use with LLM tool calling - returns structured data
    suitable for agentic workflows.

    Args:
        original: Original text
        revised: Revised text

    Returns:
        Dict with html, plaintext, word_compatible renders and summary
    """
    return {
        "html": render_html_redline(original, revised, word_level=True),
        "plaintext": render_plaintext_redline(original, revised, word_level=True),
        "word_compatible": render_word_compatible(original, revised, word_level=True),
        "summary": get_change_summary(original, revised),
        "chunks": [c.to_dict() for c in compute_diff(original, revised, word_level=True)]
    }

def compare_texts_tool(text_a: str, text_b: str) -> Dict[str, Any]:
    """
    Tool interface for comparing two texts.

    Provides a high-level comparison suitable for agentic workflows.

    Args:
        text_a: First text
        text_b: Second text

    Returns:
        Dict with similarity metrics and diff information
    """
    summary = get_change_summary(text_a, text_b)

    total_chars = max(len(text_a), len(text_b), 1)
    changes = summary["inserted_chars"] + summary["deleted_chars"]
    similarity = max(0, 100 - (changes * 100 / total_chars))

    return {
        "summary": summary,
        "similarity_percent": round(similarity, 1),
        "are_identical": not summary["has_changes"],
        "diff_count": summary["insertions"] + summary["deletions"],
        "redline_preview": render_plaintext_redline(text_a, text_b, word_level=True)[:500]
    }

def is_dmp_available() -> bool:
    """Check if diff-match-patch is available."""
    return _DMP_AVAILABLE
