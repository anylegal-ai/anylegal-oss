"""
AnyLegal Workspace Tools

Tool definitions and implementations for the agentic workspace.
Tools are called by the LLM during the agentic loop.

See ``workspace_tools.py`` for the authoritative list of active tools and
their categories. This package re-exports the tool infrastructure entry
points and the standalone diff utilities.
"""

from .workspace_tools import WORKSPACE_TOOLS, get_tool_schema
from .tool_executor import ToolExecutor, ToolResult

from .diff_tool import (
    compute_diff,
    render_html_redline,
    render_plaintext_redline,
    render_word_compatible,
    get_change_summary,
    apply_changes,
    generate_redline_tool,
    compare_texts_tool,
    DiffOperation,
    DiffChunk,
)

from .docx_tools import DOCX_TOOLS

__all__ = [

    "WORKSPACE_TOOLS",
    "get_tool_schema",
    "ToolExecutor",
    "ToolResult",

    "compute_diff",
    "render_html_redline",
    "render_plaintext_redline",
    "render_word_compatible",
    "get_change_summary",
    "apply_changes",
    "generate_redline_tool",
    "compare_texts_tool",
    "DiffOperation",
    "DiffChunk",

    "DOCX_TOOLS",
]
