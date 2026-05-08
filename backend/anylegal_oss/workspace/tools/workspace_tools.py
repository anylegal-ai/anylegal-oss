"""
Workspace Tool Definitions

Defines the tools available to the agentic workspace system.
Tool schemas are in Anthropic function calling format (input_schema).

Categories:
- Document Management (6): list_documents, read_document, create_document, create_folder, delete_document, delete_folder
- Web/Research (2): web_search, web_fetch
- Code Execution (1): run_code
- DOCX Editing (12): edit_document, clone_document, add_comment, revert_edit, get_revision_stats, accept_all_changes, reject_all_changes, accept_changes, reject_changes, instantiate_template, produce_redline
- Comparison (1): compare
- Skills/Modes (3): Skill, enter_plan_mode, exit_plan_mode
- Progress (1): todo_write
"""

import os
from typing import List, Dict, Any, Optional

# Plan mode (model-initiated multi-step planner) is opt-in in OSS — see
# `.env.example` and the ANYLEGAL_PLANNER_MODE comment. When disabled,
# enter_plan_mode / exit_plan_mode are not surfaced to the LLM at all,
# so the model can never invoke the plan-approval flow.
_PLANNER_ENABLED: bool = os.getenv("ANYLEGAL_PLANNER_MODE", "disabled").lower() == "enabled"

LIST_DOCUMENTS_TOOL = {
    "name": "list_documents",
    "description": "List all files in the workspace: uploaded documents, workspace files (anylegal.md, Playbook/positions.md), skills (read-only), and templates (user-uploaded, read-only for agent). Optionally filter by folder.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder": {
                "type": "string",
                "description": "Optional folder path to filter by (e.g., 'Clients/Acme/'). If omitted, lists all files."
            }
        },
        "required": []
    }
}

READ_DOCUMENT_TOOL = {
    "name": "read_document",
    "description": (
        "Read the content of any file in the workspace: uploaded documents (DOCX, XLSX, PPTX, PDF), workspace files "
        "(anylegal.md, Playbook/positions.md), skills (Skills/*/SKILL.md), or templates (Templates/*.docx). "
        "XLSX files return sheet data as markdown tables. PPTX files return slide text and speaker notes. "
        "For DOCX files, use view='text' (default) for plain text. Use view='xml' only for debugging.\n\n"
        "**Range params (post-edit verification):** after a batch of edits, use `around_text=` "
        "to read the affected region without pulling the whole document. Three modes (mutually "
        "exclusive — at most one):\n"
        "- `around_text='clause text'`: returns ±context_chars/2 around the first match.\n"
        "- `start_text='8.', end_text='9.'`: returns content between two anchors (inclusive).\n"
        "- `paragraph_range=[20, 35]`: returns paragraphs 20-35 (inclusive, 0-indexed).\n"
        "Range params apply to text view only; ignored for view='xml'."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File path — document UUID for uploads, or workspace path (e.g., 'anylegal.md', 'Playbook/positions.md', 'Skills/review/SKILL.md', 'Templates/NDA_Template.docx')"
            },
            "view": {
                "type": "string",
                "enum": ["text", "xml"],
                "description": (
                    "For DOCX: 'text' (default) returns plain text for reading and editing; "
                    "'xml' returns the raw document.xml (advanced debugging only). "
                    "Ignored for non-DOCX documents."
                ),
                "default": "text"
            },
            "around_text": {
                "type": "string",
                "description": (
                    "Slice the document around the first occurrence of this text. "
                    "Returns context_chars total (centered on the match). "
                    "Use after edits to verify a specific region."
                ),
            },
            "context_chars": {
                "type": "integer",
                "description": "Total character window for around_text mode. Default 2000.",
                "default": 2000,
            },
            "start_text": {
                "type": "string",
                "description": (
                    "Start anchor for explicit-range mode. Returns content from this anchor "
                    "to end_text (or EOF if end_text not provided / not found)."
                ),
            },
            "end_text": {
                "type": "string",
                "description": "End anchor for explicit-range mode (used with start_text).",
            },
            "paragraph_range": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 2,
                "maxItems": 2,
                "description": (
                    "[start_idx, end_idx] paragraph slice (inclusive, 0-indexed). "
                    "Out-of-bounds end clamps to last paragraph."
                ),
            },
        },
        "required": ["path"]
    }
}

CREATE_DOCUMENT_TOOL = {
    "name": "create_document",
    "description": (
        "Create or update workspace text files: anylegal.md (instructions) and Playbook/*.md (negotiation positions). "
        "NOT for DOCX documents — use run_python with python-docx for all document creation. "
        "Skills/ and Templates/ are read-only."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Workspace file path: 'anylegal.md', 'Playbook/commercial-contracts.md', etc. "
                    "Do NOT use for .docx paths — use run_python instead."
                )
            },
            "content": {
                "type": "string",
                "description": "File content in markdown."
            },
            "description": {
                "type": "string",
                "description": "Brief description of the file"
            }
        },
        "required": ["path", "content"]
    }
}

CREATE_FOLDER_TOOL = {
    "name": "create_folder",
    "description": (
        "Create a folder in the user's workspace. "
        "Use during /setup to scaffold a folder structure suited to the user's profile. "
        "Creates all intermediate parent folders automatically. "
        "Skills/ and Templates/ are system folders and cannot be modified."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_path": {
                "type": "string",
                "description": "Folder path to create, e.g. 'Clients/' or 'Contracts/NDAs/'. Trailing slash optional. Parent folders are created automatically."
            }
        },
        "required": ["folder_path"]
    }
}

DELETE_DOCUMENT_TOOL = {
    "name": "delete_document",
    "description": (
        "Delete a single document or workspace file. "
        "Use during /setup 'start fresh' to remove old files the user no longer wants. "
        "Always confirm with the user which specific files to delete before calling this. "
        "Cannot delete system files in Skills/ or Templates/."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path of the file to delete, e.g. 'Playbook/positions.md' or 'Clients/contract.docx'."
            }
        },
        "required": ["path"]
    }
}

DELETE_FOLDER_TOOL = {
    "name": "delete_folder",
    "description": (
        "Delete a user folder and all its contents. "
        "Use during /setup 'start fresh' to clear old folder structure. "
        "Always confirm with the user exactly which folders to delete before calling this. "
        "Protected system folders (Skills/, Templates/) cannot be deleted."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_path": {
                "type": "string",
                "description": "Folder path to delete, e.g. 'Clients/' or 'OldContracts/'. All files inside will be removed."
            }
        },
        "required": ["folder_path"]
    }
}

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "Search the web for market standards, legal precedents, regulatory requirements, "
        "or current practices. Use when the user asks about 'market standard', 'typical "
        "terms', 'best practice', or needs external research.\n\n"
        "**Always pass `jurisdiction`** so results are localized (UK, US, Singapore, UAE, "
        "etc.). If the jurisdiction is ambiguous from context, ask the user before "
        "searching — don't guess. Prefer official government and institutional sources "
        "over secondary commentary when citing results.\n\n"
        "**If a search returns no relevant results, say so explicitly** — do NOT "
        "fabricate citations to fill the gap."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - be specific and include relevant legal/business context"
            },
            "jurisdiction": {
                "type": "string",
                "description": (
                    "Relevant jurisdiction for the search (e.g., 'UK', 'US', 'SG', "
                    "'Singapore', 'GENERAL'). Always provide — unlocalized results are "
                    "rarely useful for legal research."
                )
            },
            "count": {
                "type": "integer",
                "description": "Number of results to return (1-10)",
                "default": 5,
                "minimum": 1,
                "maximum": 10
            }
        },
        "required": ["query"]
    }
}

WEB_FETCH_TOOL = {
    "name": "web_fetch",
    "description": "Fetch and extract content from a URL. Supports HTML pages and PDF documents. Use for reading legal articles, statutes, regulations, court filings, or any web page/PDF that contains relevant information.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Full URL to fetch (must start with http:// or https://)"
            },
            "extract_mode": {
                "type": "string",
                "enum": ["markdown", "text"],
                "description": "How to extract content - 'markdown' preserves formatting, 'text' is plain text",
                "default": "markdown"
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (truncates if exceeded)",
                "default": 50000
            }
        },
        "required": ["url"]
    }
}

COMPARE_TOOL = {
    "name": "compare",
    "description": "Compare two texts or two session documents. Returns structured diff, similarity percentage, and visual output. Use for redline analysis, version comparison, or counterparty revision review.",
    "input_schema": {
        "type": "object",
        "properties": {
            "text_a": {
                "type": "string",
                "description": "First text to compare (or omit if using path_a)"
            },
            "text_b": {
                "type": "string",
                "description": "Second text to compare (or omit if using path_b)"
            },
            "path_a": {
                "type": "string",
                "description": "Path to first document in session (alternative to text_a)"
            },
            "path_b": {
                "type": "string",
                "description": "Path to second document in session (alternative to text_b)"
            },
            "format": {
                "type": "string",
                "enum": ["summary", "html", "markdown"],
                "description": "Output format",
                "default": "summary"
            }
        },
        "required": []
    }
}

RUN_CODE_TOOL = {
    "name": "run_code",
    "description": (
        "Execute code in an isolated sandbox with pre-installed libraries. Supports "
        "Python 3.11 (default) and Node.js 20 — select via the `language` parameter.\n\n"
        "Python use cases: Excel read/edit/create (openpyxl), PowerPoint (python-pptx), "
        "data analysis (pandas), date/financial calculations, PDF text extraction "
        "(pymupdf4llm), charts (matplotlib), bulk OOXML edits via lxml+zipfile, any "
        "programmatic logic.\n\n"
        "Node use cases: DOCX creation with docx-js — the ONLY supported path for new "
        "Word documents. Gives you native footnotes (FootnoteReferenceRun), internal "
        "hyperlinks (Bookmark + InternalHyperlink), TableOfContents, PageNumber in "
        "headers/footers, positional tabs with leaders, multi-column sections.\n\n"
        "**File-type conventions:**\n"
        "- **DOCX creation (new document from scratch):** docx-js via `language=\"node\"` "
        "ONLY. python-docx is NOT supported for from-scratch creation — it has no API for "
        "footnotes/TOC/page-numbers and produces documents Word flags as corrupt. "
        "The `draft` skill has canonical examples.\n"
        "- **DOCX editing (existing document, including filling template placeholders):** "
        "use `edit_document` — not `run_code`. The `docx-editing` skill covers template "
        "fill and redlining.\n"
        "- **Spreadsheets (.xlsx):** first check `Templates/` for a matching template; "
        "if one exists, open and fill it. Always use Excel FORMULAS (`=SUM(...)`, "
        "`=VLOOKUP(...)`) — never hardcode calculated values. Save to "
        "`/sandbox/output/filename.xlsx` (auto-imports with PDF preview). Do NOT create "
        "HTML versions — .xlsx is previewed natively.\n"
        "- **Presentations (.pptx):** first check `Templates/` for a matching template "
        "to preserve slide master / layouts / branding. Save to `/sandbox/output/filename.pptx`. "
        "Do NOT create HTML versions.\n\n"
        "**ONE DOCUMENT = ONE `run_code` CALL** for single-doc creation — never split a "
        "document across multiple scripts. For documents too large for one call, see the "
        "long-document pattern in the `draft` skill (incremental builds via input_files).\n\n"
        "**Citation numbering in DOCX outputs:** when the script writes a Sources or "
        "References section, number it from 1 and match the inline `[1]`, `[2]`, `[3]` "
        "order in the body. NEVER continue numbering from a previous chat message — "
        "each document is its own numbering scope, starts fresh at 1.\n\n"
        "IMPORTANT: Each run is an EPHEMERAL Docker container — files from previous runs do NOT persist. "
        "To modify a document created by a previous run, pass it via input_files so it is mounted at /sandbox/input/<filename>. "
        "NEVER reference /sandbox/output/ paths from a previous run — the file will not exist. "
        "`.doc` files passed via input_files are auto-converted to `.docx`. "
        "Input workspace files at /sandbox/input/<filename>. "
        "Write output files to /sandbox/output/<filename> — they are automatically added to the workspace. "
        "DOCX outputs are validated automatically (XSD + rels + tracked-change checks). If "
        "`validation_errors` appears in the result, fix the code and retry (max 3 attempts). "
        "`validation_warnings` are informational only — do NOT retry to fix them. "
        "No network access. 120-second timeout. 512MB memory limit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": (
                    "Source code to execute. Must be self-contained. "
                    "Read input files from /sandbox/input/<filename>. "
                    "Write output files to /sandbox/output/<filename>. "
                    "Use print() (Python) or console.log() (Node) for diagnostic output — "
                    "captured in stdout.\n\n"
                    "Python pre-installed: python-docx, python-pptx, openpyxl, pandas, lxml, "
                    "matplotlib, reportlab, pymupdf4llm, python-dateutil, Pillow, tabulate, regex.\n\n"
                    "Node pre-installed: docx (docx-js 9.5.1). Other packages not available — "
                    "no network, no npm install at runtime."
                )
            },
            "language": {
                "type": "string",
                "enum": ["python", "node"],
                "description": (
                    "Interpreter that runs the code. Defaults to 'python'. Use 'node' only "
                    "for docx-js creation (native footnotes, TOC, etc.) where python-docx "
                    "is too limited."
                ),
                "default": "python",
            },
            "input_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Workspace document paths to mount in the sandbox at /sandbox/input/. "
                    "REQUIRED when modifying a document from a previous run — each sandbox is ephemeral. "
                    "DOCX blobs are extracted as files. "
                    "Example: ['contract.docx', 'Playbook/nda.md']"
                )
            },
            "description": {
                "type": "string",
                "description": "Brief description of what this code does (shown to user)"
            }
        },
        "required": ["code"]
    }
}

CLONE_DOCUMENT_TOOL = {
    "name": "clone_document",
    "description": (
        "Create the next version of a document before editing. Law firm versioning: "
        "original → v2 → v3 → v4. All versions preserved. "
        "Always pass the ORIGINAL document path — the backend automatically finds the latest "
        "version and clones FROM it to the next number. "
        "Call once at the start of each editing session, then edit_document on the new version."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path of the document to clone (UUID or workspace path)."
            },
            "target_path": {
                "type": "string",
                "description": "Path for the clone. Omit to auto-generate versioned name (e.g., Contract_v2.docx)."
            }
        },
        "required": ["source_path"]
    }
}

EDIT_DOCUMENT_TOOL = {
    "name": "edit_document",
    "description": (
        "Edit body text in an existing DOCX. This is the edit tool — "
        "use it for changing clause text, replacing defined terms, "
        "fixing typos, updating dates/amounts, deleting sections via "
        "start_text/end_text range delete, filling template "
        "placeholders. The server generates valid <w:ins>/<w:del> "
        "tracked-change markup automatically and preserves run "
        "properties (font, bold, size). Supports **bold** markdown "
        "in new_text.\n\n"
        "Call read_document(view='text') first to get the exact "
        "current text to pass as old_text. Auto-clones to _v2.docx "
        "on first edit so the original stays pristine."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path. Optional — if omitted, uses the active document (set by clone_document)."
            },
            "old_text": {
                "type": "string",
                "description": (
                    "Exact text to find and replace. Copy from read_document output. "
                    "Must be unique in the document — include enough surrounding context. "
                    "Use near_text if the same phrase appears multiple times."
                )
            },
            "new_text": {
                "type": "string",
                "description": (
                    "Replacement text. Use **bold** for bold formatting. "
                    "Empty string to delete old_text."
                )
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation of why this change is being made."
            },
            "start_text": {
                "type": "string",
                "description": "Range deletion: text at the START of the range to delete (inclusive). Use with end_text."
            },
            "end_text": {
                "type": "string",
                "description": "Range deletion: text at the END of the range to delete (inclusive). Use with start_text."
            },
            "near_text": {
                "type": "string",
                "description": "Disambiguation: text near the target when old_text appears multiple times."
            }
        },
        "required": []
    }
}

REVERT_EDIT_TOOL = {
    "name": "revert_edit",
    "description": (
        "Undo specific tracked changes by revision ID. Surgically removes the tracked change "
        "markup for the given IDs, restoring the original text. Other tracked changes are untouched. "
        "Get revision IDs from ``get_revision_stats``."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path)."
            },
            "revision_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Revision IDs to revert (from ``get_revision_stats``)."
            }
        },
        "required": ["path", "revision_ids"]
    }
}

GET_REVISION_STATS_TOOL = {
    "name": "get_revision_stats",
    "description": (
        "Get statistics about tracked changes in a DOCX document: insertion count, deletion count, "
        "authors, total changes, and revision IDs. Use to check the current state of tracked changes.\n\n"
        "Pass with_snippets=True to also get a per-revision detail list (id, type, author, date, "
        "text_snippet, context_around) — needed for picking specific IDs for "
        "accept_changes / reject_changes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path)."
            },
            "with_snippets": {
                "type": "boolean",
                "description": (
                    "When true, return per-revision detail with text snippets and context. "
                    "Default false (counts and IDs only)."
                ),
                "default": False,
            },
        },
        "required": ["path"]
    }
}

ACCEPT_CHANGES_TOOL = {
    "name": "accept_changes",
    "description": (
        "Accept SPECIFIC tracked changes by revision ID. For each ID: <w:ins> becomes permanent "
        "(insertion stays); <w:del> is dropped (deletion stays gone). For batch finalization of "
        "ALL changes, use accept_all_changes instead.\n\n"
        "Workflow: call get_revision_stats(with_snippets=True) to see each change's text and "
        "author, then pass the IDs you want to accept. Auto-clones the original to _v2 on first "
        "call (mirrors edit_document safety net). Returns accepted_ids and not_found_ids so you "
        "know which IDs landed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path)."
            },
            "revision_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of revision IDs to accept (from get_revision_stats)."
            },
        },
        "required": ["path", "revision_ids"]
    }
}

PRODUCE_REDLINE_TOOL = {
    "name": "produce_redline",
    "description": (
        "Produce a redlined comparison DOCX from two documents. The output is a Word-openable "
        "DOCX showing path_b's differences from path_a as tracked changes — for the user to "
        "review and accept/reject in Word. Routes through LibreOffice's native CompareDocuments "
        "UNO dispatcher for proper paragraph-mark / run-property / table-cell handling.\n\n"
        "When to call: user asks 'show me what changed', 'redline this against the previous "
        "version', 'produce a comparison document', etc. Distinct from `compare` (which returns "
        "a text-level diff summary for the agent to reason about, no DOCX output)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path_a": {
                "type": "string",
                "description": "Baseline document path (before).",
            },
            "path_b": {
                "type": "string",
                "description": "Revised document path (after).",
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Path for the redlined output DOCX. Name by content "
                    "(e.g. 'Acme Contract — Redline 2026-04-25.docx')."
                ),
            },
            "author": {
                "type": "string",
                "description": "Author name to attach to the tracked changes. Default 'Anylegal.ai'.",
                "default": "Anylegal.ai",
            },
        },
        "required": ["path_a", "path_b", "output_path"],
    },
}

INSTANTIATE_TEMPLATE_TOOL = {
    "name": "instantiate_template",
    "description": (
        "Create a new DOCX from a template by filling placeholders. NO tracked changes "
        "in the output — the result is a clean final document. The template is untouched.\n\n"
        "When to use: user asks to 'create a board resolution from this template', 'fill in "
        "this NDA template', 'instantiate this template with these values', etc. Output is "
        "saved at the given output_path with the model-chosen name (e.g. "
        "'Acme Board Resolution 2026-04-25.docx', not 'Template_v2.docx').\n\n"
        "Formatting preservation: each placeholder's enclosing run properties (<w:rPr> — bold, "
        "font, size) are preserved. Multi-run placeholders (e.g. '[●]' split across runs) are "
        "handled correctly.\n\n"
        "Distinct from edit_document: edit_document emits tracked changes for redline review. "
        "Use instantiate_template ONLY for template fills where the user wants a final document, "
        "not a marked-up draft. For per-placeholder review, use clone_document + edit_document "
        "(then accept_all_changes when done)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "template_path": {
                "type": "string",
                "description": "Path to the source template (e.g., 'Templates/Board_Resolution.docx').",
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Path for the new document — name by content, not '_v2'. "
                    "Example: 'Acme Board Resolution 2026-04-25.docx'."
                ),
            },
            "replacements": {
                "type": "object",
                "description": (
                    "Map of placeholder text → replacement text. Example: "
                    "{'[Disclosing Party]': 'Acme Corporation', '[Date]': '25 April 2026'}. "
                    "Each placeholder must appear in the template; missing ones are reported "
                    "in not_found.\n\n"
                    "Disambiguation: when the same token appears multiple times in the "
                    "template (e.g. '[●]' showing up at multiple placeholders), each key "
                    "must be a unique-in-document string. Include surrounding context — "
                    "e.g. 'Discount Rate is [●] %' instead of just '[●]'. Identical short "
                    "keys would only fill the first occurrence."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["template_path", "output_path", "replacements"],
    },
}

REJECT_CHANGES_TOOL = {
    "name": "reject_changes",
    "description": (
        "Reject SPECIFIC tracked changes by revision ID. For each ID: <w:ins> is dropped "
        "(insertion disappears); <w:del> is unwrapped, restoring the deleted text. For batch "
        "rejection of ALL changes, use reject_all_changes instead.\n\n"
        "Workflow: call get_revision_stats(with_snippets=True) to see each change, then pass the "
        "IDs you want to reject. Auto-clones the original to _v2 on first call. Returns "
        "rejected_ids and not_found_ids."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path)."
            },
            "revision_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of revision IDs to reject (from get_revision_stats)."
            },
        },
        "required": ["path", "revision_ids"]
    }
}

ACCEPT_ALL_CHANGES_TOOL = {
    "name": "accept_all_changes",
    "description": (
        "Accept all tracked changes in a DOCX — produces a clean document with every "
        "<w:ins> committed and every <w:del> removed. Routes through LibreOffice so every "
        "OOXML edge case (nested changes, complex formatting, paragraph marks, table cells, "
        "content controls, comment anchors) is handled correctly.\n\n"
        "When to call: user asks to 'finalize', 'accept all changes', 'clean up', 'apply all "
        "edits', or the review/redlining workflow is complete and the user wants the final "
        "version. Pass output_path to save as a new document; omit to update in place."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path) of the DOCX with tracked changes."
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optional workspace path to save the cleaned DOCX as a new document "
                    "(e.g. 'Contract_Clean.docx'). If omitted, the source document is updated in place."
                )
            }
        },
        "required": ["path"]
    }
}

ADD_COMMENT_TOOL = {
    "name": "add_comment",
    "description": (
        "Add a margin comment to a DOCX document. Handles the four-file "
        "coordination Word requires (comments.xml, commentsExtended.xml, "
        "commentsIds.xml, commentsExtensible.xml) plus the relationship + "
        "content-type registrations, so one tool call produces a fully-valid "
        "commented document.\n\n"
        "When to call: user asks you to 'comment on', 'flag', 'annotate', or "
        "'leave a note about' specific text in a document. For replies to "
        "existing comments, pass parent_id."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path).",
            },
            "target_text": {
                "type": "string",
                "description": (
                    "Text in the document to anchor the comment to. The "
                    "balloon appears next to this text in Word."
                ),
            },
            "comment_text": {
                "type": "string",
                "description": "The comment body — what shows in the margin.",
            },
            "author": {
                "type": "string",
                "description": (
                    "Comment author. Default 'Anylegal.ai'. Use the user's "
                    "name from anylegal.md if available."
                ),
                "default": "Anylegal.ai",
            },
            "initials": {
                "type": "string",
                "description": "2-3 character author initials. Default 'A'.",
                "default": "A",
            },
            "parent_id": {
                "type": "integer",
                "description": (
                    "Parent comment id for threaded replies. Omit for a new "
                    "top-level comment."
                ),
            },
            "near_text": {
                "type": "string",
                "description": "Disambiguator when target_text matches multiple locations.",
            },
        },
        "required": ["path", "target_text", "comment_text"],
    },
}

REJECT_ALL_CHANGES_TOOL = {
    "name": "reject_all_changes",
    "description": (
        "Reject all tracked changes in a DOCX — restores the document to its state before "
        "any tracked edits were made. Routes through LibreOffice (same reliability rationale "
        "as accept_all_changes).\n\n"
        "When to call: user asks to 'reject all', 'revert all changes', 'undo my edits', or "
        "to get back to the original version of a document that's been edited with tracked "
        "changes. For reverting SPECIFIC edits by revision ID, use revert_edit instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Document path (UUID or workspace file path) of the DOCX with tracked changes."
            },
            "output_path": {
                "type": "string",
                "description": (
                    "Optional workspace path to save the restored DOCX as a new document. "
                    "If omitted, the source document is updated in place."
                )
            }
        },
        "required": ["path"]
    }
}

from .todo_tool import TODO_WRITE_TOOL
from .mode_tools import ENTER_PLAN_MODE_TOOL, EXIT_PLAN_MODE_TOOL

SKILL_TOOL: Dict[str, Any] = {
    "name": "Skill",
    "description": (
        "Invoke a skill by name. Skills contain required procedures for document "
        "tasks (drafting, review, comparison, QA, research). The skill body is "
        "returned as the tool result; follow it on the next turn.\n\n"
        "**When to call:**\n"
        "- User references a slash command like `/draft`, `/review`, `/qa`, "
        "`/research`, `/compare`, `/setup`.\n"
        "- User's task matches a skill even without the slash prefix (e.g. "
        "\"draft an NDA\" → `Skill(skill=\"draft\")`).\n"
        "- You need the procedure before starting any document task; the "
        "skills contain required steps that the system prompt deliberately "
        "does NOT duplicate.\n\n"
        "**Rules:**\n"
        "- **BLOCKING REQUIREMENT:** call this tool BEFORE generating any "
        "other response about a document task. Do NOT describe what a skill "
        "does without actually invoking it.\n"
        "- Skills scope the tool pool — once invoked, only the tools the "
        "skill declares (plus a small always-on set) are available to you "
        "until the next user turn.\n"
        "- Only invoke a skill listed in the 'Available Skills' section of "
        "the system prompt. Never guess a skill name."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": (
                    "Skill name, e.g. 'draft', 'review', 'qa', 'research', "
                    "'compare', 'docx-editing', 'setup'. Must match a skill "
                    "listed in Available Skills."
                ),
            },
            "args": {
                "type": "string",
                "description": (
                    "Optional arguments passed with the slash command. "
                    "Prepended to the skill body as a context header."
                ),
            },
        },
        "required": ["skill"],
    },
}

SEARCH_WORKSPACE_TOOL: Dict[str, Any] = {
    "name": "search_workspace",
    "description": (
        "BM25 full-text search across the user's workspace documents AND the "
        "compiled wiki pages. Use this FIRST for cross-document questions "
        "(\"what indemnification caps have I agreed?\", \"which contracts mention "
        "termination for convenience?\") — it's free (no LLM cost) and avoids "
        "loading every doc.\n\n"
        "Returns up to `top_k` results sorted by relevance, each with a snippet "
        "showing the matched terms in context. After locating relevant docs, "
        "use `read_document` for full text or `read_wiki_page` for the compiled "
        "summary.\n\n"
        "If the wiki has not been compiled yet, results will only include source "
        "documents — still useful, just narrower."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query — keywords or phrases. Legal terms work well (e.g. 'liability cap', 'force majeure', 'data processing').",
            },
            "top_k": {
                "type": "integer",
                "description": "Maximum results to return (1-50). Default 10.",
                "default": 10,
                "minimum": 1,
                "maximum": 50,
            },
        },
        "required": ["query"],
    },
}

READ_WIKI_PAGE_TOOL: Dict[str, Any] = {
    "name": "read_wiki_page",
    "description": (
        "Read a single compiled wiki page by slug. The page is an LLM-generated "
        "summary of one source document, with extracted parties, jurisdiction, "
        "key clauses, and [[backlinks]] to related documents — typically much "
        "shorter than the source.\n\n"
        "Use after `search_workspace` returns a `wiki_page` hit, or after "
        "`list_wiki_pages` shows a slug you want to load. For full source text, "
        "use `read_document` on the page's `source` frontmatter field instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "Page slug, e.g. 'contracts/acme-msa', 'topics/data-residency'.",
            },
        },
        "required": ["slug"],
    },
}

LIST_WIKI_PAGES_TOOL: Dict[str, Any] = {
    "name": "list_wiki_pages",
    "description": (
        "List compiled wiki pages, optionally filtered by category. Returns "
        "pages grouped by category with title, parties, and jurisdiction "
        "metadata. Use to browse what the wiki knows about, without loading "
        "every page.\n\n"
        "Categories: 'contracts', 'statutes', 'cases', 'memos', 'topics'. "
        "Pass 'indexes' to get the list of cross-cutting indexes "
        "(clause_library, by_party, by_jurisdiction, by_type, precedent_map) "
        "available for browsing via the workspace UI."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Optional category filter. Omit to get all categories.",
                "enum": ["contracts", "statutes", "cases", "memos", "topics", "indexes"],
            },
        },
        "required": [],
    },
}

APPEND_WIKI_NOTE_TOOL: Dict[str, Any] = {
    "name": "append_wiki_note",
    "description": (
        "Append a timestamped note to Anylegal.ai's memory of this matter. "
        "The note shows up in the Memory tab and is read by future agent "
        "turns about this workspace. Cheap, no LLM cost.\n\n"
        "**Two routing modes by `slug`:**\n"
        "- **Provide `slug`** (e.g. `'contracts/acme-msa'`) when the note is "
        "about that specific document. Use after `edit_document` adds a new "
        "clause, after `accept_changes` ratifies a redline, or after research "
        "uncovers something doc-specific (e.g. counterparty's standard "
        "position on a clause).\n"
        "- **Omit `slug`** when the note is a cross-cutting workspace insight "
        "not tied to one doc — counterparty intel that crosses deals, user "
        "preferences (e.g. \"prefers UK law for SaaS\"), strategic context, "
        "stakeholder info. These land in the workspace-level journal and "
        "inject into every future turn about this matter.\n\n"
        "**Notes are descriptive facts only** — never severity tags, never "
        "\"this is wrong\" judgments. \"User asked about cap structure today\" "
        "yes; \"this clause is too restrictive\" no (that's an evaluation; "
        "keep it in chat). Notes are additive — they never overwrite the "
        "compiled summary or earlier notes. Keep each note focused and short "
        "(1-3 sentences).\n\n"
        "**Tag every note with `type`** so future retrievals can filter:\n"
        "- `\"user\"` — facts about the lawyer themselves: role, jurisdiction, "
        "expertise. Example: *\"User is a corporate associate at a UAE firm, "
        "8 years VC experience.\"*\n"
        "- `\"feedback\"` — how Anylegal.ai should behave: format, tone, "
        "process. Example: *\"User wants all liability caps flagged HIGH RISK.\"*\n"
        "- `\"project\"` (default) — facts about the matter: parties, "
        "decisions, timing, intel. Example: *\"Acme's Jane Doe is the "
        "negotiator; she's lenient on caps but firm on IP.\"*\n"
        "- `\"reference\"` — pointers to external resources. Example: "
        "**Do NOT save** as notes (these are noise):\n"
        "- Things derivable from doc content (the wiki has them).\n"
        "- Audit-trail of edits (the doc's track-changes captures it).\n"
        "- Things already in `anylegal.md` or `Playbook/*.md` (already injected).\n"
        "- Ephemeral chat state (\"user said hi\", \"acknowledging request\").\n"
        "- Evaluative claims (\"this is risky\") — keep in chat where the user can interrogate."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {
                "type": "string",
                "description": "Optional. Wiki page slug, e.g. 'contracts/acme-msa'. Omit for workspace-level notes (cross-cutting insights). Use list_wiki_pages to find slugs.",
            },
            "note": {
                "type": "string",
                "description": "The fact to record. 1-3 sentences, lawyer-readable. Descriptive only — what happened, what was learned, what was decided. Not evaluations.",
            },
            "type": {
                "type": "string",
                "enum": ["user", "feedback", "project", "reference"],
                "description": "Taxonomy tag for retrieval. user=facts about the lawyer; feedback=how AI should behave; project=facts about the matter (DEFAULT); reference=external resource pointers.",
            },
        },
        "required": ["note"],
    },
}

UPDATE_WIKI_PAGE_TOOL: Dict[str, Any] = {
    "name": "update_wiki_page",
    "description": (
        "Replace a wiki page's compiled summary body. Use SPARINGLY — only "
        "when the existing summary is actively misleading after a major doc "
        "restructure. For incremental changes, use `append_wiki_note` "
        "instead (additive, lower-risk).\n\n"
        "Your replacement should be markdown: 1-2 paragraphs of summary, "
        "followed by a bullet list of key clauses and values. Do NOT "
        "duplicate the frontmatter (parties, jurisdiction) in the body — "
        "those are stored separately."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Wiki page slug."},
            "content": {
                "type": "string",
                "description": "New markdown summary body. Replaces the existing compiled_body.",
            },
        },
        "required": ["slug", "content"],
    },
}

SET_WIKI_METADATA_TOOL: Dict[str, Any] = {
    "name": "set_wiki_metadata",
    "description": (
        "Patch a single frontmatter field on a wiki page. Use when you've "
        "established a fact that the compile didn't extract correctly — "
        "e.g. the counterparty was misidentified, the governing law is "
        "different from what the doc literally says, or a subject area was "
        "missed.\n\n"
        "Allowed keys: parties (list), jurisdiction (string), "
        "effective_date (ISO date string), subject_areas (list), title "
        "(string)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Wiki page slug."},
            "key": {
                "type": "string",
                "enum": ["parties", "jurisdiction", "effective_date", "subject_areas", "title"],
            },
            "value": {
                "description": "New value for the field. Type depends on key (list for parties/subject_areas, string for others).",
            },
        },
        "required": ["slug", "key", "value"],
    },
}

DELETE_WIKI_PAGE_TOOL: Dict[str, Any] = {
    "name": "delete_wiki_page",
    "description": (
        "Remove a wiki page. Use ONLY when the source document has been "
        "deleted from the workspace; for everything else (rename, move, "
        "update content), prefer the other edit tools."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "slug": {"type": "string", "description": "Wiki page slug to remove."},
        },
        "required": ["slug"],
    },
}

SUGGEST_INSTRUCTION_TOOL: Dict[str, Any] = {
    "name": "suggest_instruction",
    "description": (
        "Propose an addition to the user's `anylegal.md` instructions. This "
        "tool DOES NOT write the file — it surfaces a chat card with the "
        "proposed text and an 'Add to instructions' button. The user clicks "
        "the button if they accept; the AI never auto-writes anylegal.md.\n\n"
        "**Use when** chat surfaces a durable preference the user has stated "
        "(or strongly implied) that should govern future sessions:\n"
        "- *\"I always want UK-law fallback for cross-border SaaS deals.\"*\n"
        "- *\"For Acme matters, default the liability cap to 12 months of fees.\"*\n"
        "- *\"Use UK English spelling in every doc.\"*\n\n"
        "**Do NOT use** for:\n"
        "- Transient observations (those go in chat as prose).\n"
        "- Per-doc facts (use `append_wiki_note` with a slug instead).\n"
        "- Cross-cutting workspace notes (use `append_wiki_note` without a slug — that's the AI's journal).\n\n"
        "Provide a `rationale` (one sentence) explaining why the user benefits "
        "— the chat card surfaces it above the proposed text so the user can "
        "decide quickly whether to accept."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "The instruction line to propose. One sentence, imperative voice, written for the AI to follow.",
            },
            "rationale": {
                "type": "string",
                "description": "1-sentence justification shown to the user above the button. Lawyer-readable.",
            },
            "target_path": {
                "type": "string",
                "description": "Optional. Folder-scoped target (e.g. 'Clients/Acme/anylegal.md'). Defaults to root anylegal.md.",
            },
        },
        "required": ["text", "rationale"],
    },
}

WORKSPACE_TOOLS: List[Dict[str, Any]] = [

    LIST_DOCUMENTS_TOOL,
    READ_DOCUMENT_TOOL,
    CREATE_DOCUMENT_TOOL,                                                                                               
    CREATE_FOLDER_TOOL,
    DELETE_DOCUMENT_TOOL,
    DELETE_FOLDER_TOOL,

    WEB_SEARCH_TOOL,
    WEB_FETCH_TOOL,

    RUN_CODE_TOOL,

    CLONE_DOCUMENT_TOOL,
    EDIT_DOCUMENT_TOOL,
    ADD_COMMENT_TOOL,
    REVERT_EDIT_TOOL,
    GET_REVISION_STATS_TOOL,
    ACCEPT_ALL_CHANGES_TOOL,
    REJECT_ALL_CHANGES_TOOL,
    ACCEPT_CHANGES_TOOL,
    REJECT_CHANGES_TOOL,
    INSTANTIATE_TEMPLATE_TOOL,
    PRODUCE_REDLINE_TOOL,

    COMPARE_TOOL,

    SEARCH_WORKSPACE_TOOL,
    READ_WIKI_PAGE_TOOL,
    LIST_WIKI_PAGES_TOOL,
    APPEND_WIKI_NOTE_TOOL,
    UPDATE_WIKI_PAGE_TOOL,
    SET_WIKI_METADATA_TOOL,
    DELETE_WIKI_PAGE_TOOL,
    SUGGEST_INSTRUCTION_TOOL,

    TODO_WRITE_TOOL,

    *([ENTER_PLAN_MODE_TOOL, EXIT_PLAN_MODE_TOOL] if _PLANNER_ENABLED else []),

    SKILL_TOOL,
]

ALWAYS_ON_TOOLS = frozenset(
    {"Skill", "todo_write"}
    | ({"enter_plan_mode", "exit_plan_mode"} if _PLANNER_ENABLED else set())
)

PLAN_MODE_TOOL_NAMES = {
    "list_documents",
    "read_document",
    "web_search",
    "web_fetch",
    "compare",
    "todo_write",
    "exit_plan_mode",
    "Skill",
}

_TOOL_MAP: Dict[str, Dict[str, Any]] = {
    tool["name"]: tool
    for tool in WORKSPACE_TOOLS
}

def get_workspace_tools() -> List[Dict[str, Any]]:
    """Return the model-facing tool pool."""
    return list(WORKSPACE_TOOLS)

def get_tool_schema(name: str) -> Optional[Dict[str, Any]]:
    """Get the schema for a specific tool by name."""
    return _TOOL_MAP.get(name)

def get_tools_for_skill(tool_names: List[str]) -> List[Dict[str, Any]]:
    """Get tool schemas for a list of tool names (used by skills)."""
    return [_TOOL_MAP[name] for name in tool_names if name in _TOOL_MAP]

def get_all_tool_names() -> List[str]:
    """Get list of all available tool names."""
    return list(_TOOL_MAP.keys())

TOOL_CATEGORIES = {
    "document_management": ["list_documents", "read_document", "create_document", "create_folder", "delete_document", "delete_folder"],
    "web_research": ["web_search", "web_fetch"],
    "code_execution": ["run_code"],
    "docx_editing": ["edit_document", "clone_document", "add_comment", "revert_edit", "get_revision_stats", "accept_all_changes", "reject_all_changes", "accept_changes", "reject_changes", "instantiate_template", "produce_redline"],
    "comparison": ["compare"],
}
