"""
WorkspaceSession - Multi-document state management for agentic workspace.

Manages in-memory documents, active document tracking, and playbook context
for the agentic chat system.
"""

import uuid
import re
import unicodedata
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Any, Set, Tuple

def normalize_text(text: str) -> str:
    """
    Normalize text for matching - handles common encoding differences.

    Normalizes:
    - Non-breaking spaces → regular spaces
    - Various dashes (em-dash, en-dash, minus) → standard hyphen
    - Smart quotes → straight quotes
    - Unicode normalization (NFC form)
    - Multiple whitespace → single space
    """

    text = unicodedata.normalize('NFC', text)

    text = text.replace('\u00a0', ' ')                      
    text = text.replace('\u2007', ' ')                
    text = text.replace('\u202f', ' ')                         
    text = text.replace('\u200b', '')                     

    text = text.replace('\u2013', '-')           
    text = text.replace('\u2014', '-')           
    text = text.replace('\u2212', '-')              

    text = text.replace('\u2018', "'")                     
    text = text.replace('\u2019', "'")                      
    text = text.replace('\u201c', '"')                     
    text = text.replace('\u201d', '"')                      

    text = re.sub(r'\s+', ' ', text)

    return text

def find_normalized_match(content: str, search_text: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Find text in content using normalized matching.

    Returns (start, end) indices in the original content, or (None, None) if not found.
    """
    norm_content = normalize_text(content)
    norm_search = normalize_text(search_text)

    idx = norm_content.find(norm_search)
    if idx == -1:
        return None, None

    orig_idx = 0
    norm_idx = 0

    while norm_idx < idx and orig_idx < len(content):

        norm_char = normalize_text(content[orig_idx])
        if norm_char and not norm_char.isspace():
            norm_idx += len(norm_char)
        elif norm_char == ' ':
            norm_idx += 1
        orig_idx += 1

    start = orig_idx

    target_end = norm_idx + len(norm_search)
    while norm_idx < target_end and orig_idx < len(content):
        norm_char = normalize_text(content[orig_idx])
        if norm_char and not norm_char.isspace():
            norm_idx += len(norm_char)
        elif norm_char == ' ':
            norm_idx += 1
        orig_idx += 1

    end = orig_idx

    return start, end

@dataclass
class DocumentMeta:
    """Metadata and content for a document in the workspace."""
    content: str                                     
    description: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    modified_at: datetime = field(default_factory=datetime.utcnow)

    docx_blob: Optional[bytes] = None                                                     
    format: str = "html"                                                                 
    is_synced: bool = True                                     

    binary_blob: Optional[bytes] = None                                                   
    mime_type: Optional[str] = None                                        

    _document_xml: Optional[str] = field(default=None, repr=False)

    finalized_at: Optional[datetime] = None

    @property
    def document_xml(self) -> Optional[str]:
        """
        Pretty-printed word/document.xml for LLM editing.

        Lazily extracted from docx_blob on first access, then cached.
        """
        if self._document_xml is None and self.docx_blob is not None:
            from .docx_xml_service import extract_document_xml
            self._document_xml = extract_document_xml(self.docx_blob)
        return self._document_xml

    def update_content(self, new_content: str, mark_unsynced: bool = True) -> None:
        """Update HTML content and modification timestamp."""
        self.content = new_content
        self.modified_at = datetime.now(timezone.utc)
        if mark_unsynced and self.docx_blob is not None:
            self.is_synced = False

    def update_docx(self, docx_bytes: bytes, html_content: Optional[str] = None) -> None:
        """Update DOCX blob and optionally sync HTML."""
        self.docx_blob = docx_bytes
        self.format = "docx"
        self.modified_at = datetime.now(timezone.utc)

        self._document_xml = None

        self.finalized_at = None
        if html_content is not None:
            self.content = html_content
            self.is_synced = True
        else:
            self.is_synced = False

    def mark_finalized(self) -> None:
        """Mark this working copy as finalized. See Option B versioning
        comment on the finalized_at field. Called by accept_all_changes /
        reject_all_changes when no output_path is supplied.
        """
        self.finalized_at = datetime.now(timezone.utc)

    def clear_finalized(self) -> None:
        """Reset the finalize marker — called when the working copy receives
        a new mutating op (edit_document, accept_changes, reject_changes,
        revert_edit, add_comment). Without this, the next edit on the
        original would bump to a new version even though the lawyer is
        still iterating on the same round.
        """
        self.finalized_at = None

    def update_document_xml(self, new_xml: str) -> None:
        """
        Apply an edited document.xml: repack blob, invalidate cache.

        Called after edit_document modifies the XML string.
        The cache is invalidated so the next access re-extracts clean
        pretty-printed XML from the repacked blob (with fresh run merging).
        """
        from .docx_xml_service import repack_docx
        self.docx_blob = repack_docx(self.docx_blob, new_xml)
        self._document_xml = None                                          
        self.modified_at = datetime.now(timezone.utc)
        self.is_synced = False

        self.finalized_at = None

    def mark_synced(self) -> None:
        """Mark HTML and DOCX as synchronized."""
        self.is_synced = True

class WorkspaceSession:
    """
    Manages the state of a user's workspace session.

    Supports multiple documents in memory, with one active document
    and optional playbook context for contract review.
    """

    _UNSET = object()                                                    

    NO_INSTRUCTIONS_FOLDERS = {"Templates", "Playbook", "Skills"}

    def __init__(
        self,
        user_id: int,
        session_id: Optional[str] = None,
        playbook: Any = _UNSET
    ):
        self.user_id = user_id
        self.session_id = session_id or str(uuid.uuid4())
        self.documents: Dict[str, DocumentMeta] = {}
        self.active_document: Optional[str] = None
        self.workspace_files: Dict[str, str] = {}                                                 
        self.folders: Set[str] = set()                                                  
        self.created_at = datetime.now(timezone.utc)
        self.context: Dict[str, Any] = {}                                                         

        if playbook is self._UNSET:
            self.folders.add("Playbook/")
            self.playbook = None
        else:

            self.playbook = playbook
            if self.playbook:
                self.workspace_files["Playbook/positions.md"] = self.playbook
                self.folders.add("Playbook/")

    @property
    def agents_md(self) -> Optional[str]:
        """Root-level anylegal.md content. Reads from workspace_files['anylegal.md']."""
        return self.workspace_files.get("anylegal.md")

    @agents_md.setter
    def agents_md(self, value: Optional[str]) -> None:
        """Set root-level anylegal.md. Stores in workspace_files['anylegal.md']."""
        if value is None:
            self.workspace_files.pop("anylegal.md", None)
        else:
            self.workspace_files["anylegal.md"] = value

    def add_document(
        self,
        path: str,
        content: str,
        description: str = "",
        set_active: bool = True
    ) -> None:
        """Add or update a document in the workspace."""
        if path in self.documents:
            self.documents[path].update_content(content)
            if description:
                self.documents[path].description = description
        else:
            self.documents[path] = DocumentMeta(
                content=content,
                description=description
            )

        if set_active:
            self.active_document = path

    def get_document(self, path: str) -> Optional[DocumentMeta]:
        """Get a document by path."""
        return self.documents.get(path)

    def get_document_content(self, path: str) -> Optional[str]:
        """Get just the content of a document."""
        doc = self.documents.get(path)
        return doc.content if doc else None

    def remove_document(self, path: str) -> bool:
        """Remove a document from the workspace."""
        if path in self.documents:
            del self.documents[path]
            if self.active_document == path:

                self.active_document = next(iter(self.documents.keys()), None)
            return True
        return False

    def list_documents(self) -> List[Dict[str, Any]]:
        """List all documents with metadata."""
        return [
            {
                "path": path,
                "description": doc.description,
                "created_at": doc.created_at.isoformat(),
                "modified_at": doc.modified_at.isoformat(),
                "size": len(doc.content),
                "is_active": path == self.active_document,

                "format": doc.format,                    
                "has_docx": doc.docx_blob is not None,
                "is_synced": doc.is_synced,
            }
            for path, doc in self.documents.items()
        ]

    def set_active_document(self, path: str) -> bool:
        """Set the active document."""
        if path in self.documents:
            self.active_document = path
            return True
        return False

    def edit_document(
        self,
        path: str,
        old_text: str,
        new_text: str
    ) -> Dict[str, Any]:
        """
        Find and replace text in a document.

        First tries exact match, then falls back to normalized matching
        to handle encoding differences (smart quotes, non-breaking spaces, etc.)

        Returns:
            Dict with success status and details
        """
        doc = self.documents.get(path)
        if not doc:
            return {
                "success": False,
                "error": f"Document not found: {path}"
            }

        if old_text in doc.content:
            count = doc.content.count(old_text)
            if count > 1:
                return {
                    "success": False,
                    "error": f"Multiple matches found ({count}). Provide more context to make the match unique.",
                    "matches": count
                }

            new_content = doc.content.replace(old_text, new_text, 1)
            doc.update_content(new_content)

            return {
                "success": True,
                "path": path,
                "replaced": True,
                "old_text": old_text,                                                          
                "new_text": new_text,                                                          
                "old_length": len(old_text),
                "new_length": len(new_text),
                "match_type": "exact"
            }

        start, end = find_normalized_match(doc.content, old_text)

        if start is not None and end is not None:

            norm_content = normalize_text(doc.content)
            norm_search = normalize_text(old_text)
            count = norm_content.count(norm_search)

            if count > 1:
                return {
                    "success": False,
                    "error": f"Multiple matches found ({count}) after normalization. Provide more context.",
                    "matches": count,
                    "hint": "The text was found but appears multiple times. Add surrounding context."
                }

            actual_matched = doc.content[start:end]

            new_content = doc.content[:start] + new_text + doc.content[end:]
            doc.update_content(new_content)

            return {
                "success": True,
                "path": path,
                "replaced": True,
                "old_text": actual_matched,                                                  
                "new_text": new_text,                                                     
                "old_length": len(old_text),
                "new_length": len(new_text),
                "match_type": "normalized",
                "note": "Matched after normalizing special characters (quotes, dashes, spaces)"
            }

        norm_search = normalize_text(old_text)
        search_preview = norm_search[:50] + "..." if len(norm_search) > 50 else norm_search

        partial_matches = []
        words = norm_search.split()[:3]                 
        if words:
            first_phrase = ' '.join(words)
            norm_content = normalize_text(doc.content)
            if first_phrase in norm_content:
                idx = norm_content.find(first_phrase)
                context = norm_content[max(0, idx-20):idx+len(first_phrase)+50]
                partial_matches.append(f"Found start of text near: '...{context}...'")

        return {
            "success": False,
            "error": "Text to replace not found in document",
            "searched_for": search_preview,
            "hint": "Ensure text matches exactly. Read the document first to get exact text.",
            "partial_matches": partial_matches if partial_matches else None
        }

    def set_context(self, key: str, value: Any) -> None:
        """Set a context value (e.g., representing, jurisdiction)."""
        self.context[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self.context.get(key, default)

    def set_playbook(self, playbook_content: str) -> None:
        """Set the playbook content (legacy — delegates to workspace_files)."""
        self.workspace_files["Playbook/positions.md"] = playbook_content
        self.folders.add("Playbook/")
        self.playbook = playbook_content                                              

    def build_playbook_manifest(self) -> Optional[str]:
        """Build a lightweight manifest of all playbook files for the system prompt.

        Scans workspace_files for Playbook/*.md entries, extracts the H1 heading
        (first line starting with '# ') from each file as its description.
        Playbook/ only supports markdown files (uploads restricted on frontend).

        Returns:
            Markdown string with table of playbook files, or None if no playbook files exist.
        """
        playbook_files = []
        for path, content in sorted(self.workspace_files.items()):
            if not path.startswith("Playbook/") or not path.endswith(".md"):
                continue
            if path.endswith("/anylegal.md"):
                continue
            filename = path.split("/", 1)[1]

            description = ""
            for line in (content or "").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    description = stripped[2:].strip()
                    break
            if not description:
                description = filename.replace(".md", "").replace("-", " ").title()
            playbook_files.append((filename, description))

        if not playbook_files:
            return None

        lines = [
            "## Available Playbooks",
            "",
            "The Playbook/ folder contains your organization's negotiating positions.",
            'Use `read_document("Playbook/<filename>")` to load the relevant playbook(s) before reviewing or drafting.',
            "Pick based on contract type, jurisdiction, client, or deal context.",
            "",
            "| File | Description |",
            "|------|-------------|",
        ]
        for filename, desc in playbook_files:
            lines.append(f"| {filename} | {desc} |")

        return "\n".join(lines)

    def match_playbooks(self, active_doc_path: Optional[str]) -> List[Tuple[str, str]]:
        """Return playbook (path, content) pairs whose YAML-frontmatter `paths:`
        glob matches the active doc.

        Implements path-scoped instruction files. A playbook
        without frontmatter (or without `paths:`) does NOT auto-inject — the
        agent can still fetch it via `read_document("Playbook/<file>.md")`,
        and the existing `build_playbook_manifest()` still lists it.

        `paths:` value can be a list or a comma-separated string of fnmatch
        patterns (e.g. `paths: "contracts/*saas*, contracts/*subscription*"`).
        """
        import fnmatch
        if not active_doc_path:
            return []
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError:
            return []

        out: List[Tuple[str, str]] = []
        for path, content in sorted(self.workspace_files.items()):
            if not path.startswith("Playbook/") or not path.endswith(".md"):
                continue
            if path.endswith("/anylegal.md"):
                continue
            if not isinstance(content, str) or not content.startswith("---"):
                continue

            end = content.find("\n---", 3)
            if end == -1:
                continue
            try:
                fm = yaml.safe_load(content[3:end]) or {}
            except Exception:
                continue
            if not isinstance(fm, dict):
                continue
            patterns = fm.get("paths")
            if isinstance(patterns, str):
                patterns = [p.strip() for p in patterns.split(",") if p.strip()]
            if not isinstance(patterns, list) or not patterns:
                continue
            for pat in patterns:
                if not isinstance(pat, str):
                    continue
                if fnmatch.fnmatchcase(active_doc_path, pat):

                    body = content[end + 4:].lstrip("\n")
                    out.append((path, body))
                    break
        return out

    def set_agents_md(self, content: str) -> None:
        """Set the root-level anylegal.md content (delegates to agents_md property)."""
        self.agents_md = content

    def set_workspace_file(self, path: str, content: str) -> None:
        """Set an arbitrary workspace file (e.g., Playbook/positions.md).

        Rejects anylegal.md inside NO_INSTRUCTIONS_FOLDERS.
        """
        if path.endswith("/anylegal.md"):
            top_folder = path.split("/")[0]
            if top_folder in self.NO_INSTRUCTIONS_FOLDERS:
                return                   
        self.workspace_files[path] = content

    def get_workspace_file(self, path: str) -> Optional[str]:
        """Get a workspace file's content by path."""
        return self.workspace_files.get(path)

    def create_folder(self, folder_path: str) -> None:
        """Create an explicit empty folder. Intermediate parents are created automatically."""
        path = folder_path.replace("\\", "/").strip("/") + "/"

        parts = path.strip("/").split("/")
        accumulated = ""
        for part in parts:
            accumulated = f"{accumulated}{part}/"
            self.folders.add(accumulated)

    PROTECTED_FOLDERS = {"Playbook", "Templates", "Skills"}

    def delete_folder(self, folder_path: str) -> int:
        """
        Delete a folder and all its contents.

        Returns the number of documents deleted.
        Raises ValueError for protected system folders.

        Protection rules:
        - Skills/: fully locked — neither the root nor any child can be deleted
        - Playbook/, Templates/: root is protected, but children (subfolders/files) can be deleted
        """
        prefix = folder_path.replace("\\", "/").strip("/") + "/"
        top_folder = prefix.split("/")[0]

        if top_folder == "Skills":
            raise ValueError("Cannot delete system folder 'Skills'.")

        if prefix in {"Playbook/", "Templates/"}:
            raise ValueError(f"Cannot delete system folder '{top_folder}'.")

        doc_paths = [p for p in self.documents if p.startswith(prefix)]
        for p in doc_paths:
            del self.documents[p]

        wf_paths = [p for p in self.workspace_files if p.startswith(prefix)]
        for p in wf_paths:
            del self.workspace_files[p]

        if "Playbook/positions.md" in wf_paths:
            self.playbook = None

        folder_paths = [f for f in self.folders if f.startswith(prefix)]
        for f in folder_paths:
            self.folders.discard(f)
        self.folders.discard(prefix)

        if self.active_document and self.active_document.startswith(prefix):
            self.active_document = next(iter(self.documents.keys()), None)
        return len(doc_paths)

    def rename_folder(self, old_path: str, new_path: str) -> bool:
        """Rename a folder, updating all document paths and workspace_files underneath."""
        old_prefix = old_path.replace("\\", "/").strip("/") + "/"
        new_prefix = new_path.replace("\\", "/").strip("/") + "/"

        for old_doc in [p for p in self.documents if p.startswith(old_prefix)]:
            new_doc = new_prefix + old_doc[len(old_prefix):]
            self.documents[new_doc] = self.documents.pop(old_doc)
            if self.active_document == old_doc:
                self.active_document = new_doc

        for old_wf in [p for p in self.workspace_files if p.startswith(old_prefix)]:
            new_wf = new_prefix + old_wf[len(old_prefix):]
            self.workspace_files[new_wf] = self.workspace_files.pop(old_wf)

        for old_f in [f for f in self.folders if f.startswith(old_prefix)]:
            self.folders.discard(old_f)
            self.folders.add(new_prefix + old_f[len(old_prefix):])

        self.folders.discard(old_prefix)
        self.folders.add(new_prefix)
        return True

    def move_document(self, old_path: str, new_path: str) -> bool:
        """Move/rename a document from one path to another."""
        if old_path not in self.documents:
            return False
        self.documents[new_path] = self.documents.pop(old_path)
        if self.active_document == old_path:
            self.active_document = new_path
        return True

    def get_anylegal_cascade(self, document_path: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Collect anylegal.md files from root to the folder containing document_path.

        Returns list of (label, content) tuples, most-general first.

        Example for document_path="Clients/Acme/NDA/contract.docx":
          [("Workspace", <root anylegal.md>),
           ("Clients", <Clients/anylegal.md>),
           ("Clients/Acme", <Clients/Acme/anylegal.md>),
           ("Clients/Acme/NDA", <Clients/Acme/NDA/anylegal.md>)]
        """
        cascade: List[Tuple[str, str]] = []

        root_content = self.workspace_files.get("anylegal.md")
        if root_content and root_content.strip():
            cascade.append(("Workspace", root_content))

        if not document_path:
            return cascade

        parts = document_path.replace("\\", "/").split("/")
        folder_parts = parts[:-1]                   

        accumulated = ""
        for segment in folder_parts:
            accumulated = f"{accumulated}{segment}/" if accumulated else f"{segment}/"
            anylegal_key = f"{accumulated}anylegal.md"
            content = self.workspace_files.get(anylegal_key)
            if content and content.strip():
                cascade.append((accumulated.rstrip("/"), content))

        return cascade

    @staticmethod
    def validate_path(path: str) -> bool:
        """Reject path traversal and invalid paths."""
        if not path:
            return False
        if '..' in path:
            return False
        if path.startswith('/') or path.startswith('\\'):
            return False
        if '\x00' in path:
            return False

        segments = path.replace("\\", "/").split("/")
        for i, s in enumerate(segments):
            if s == '.' or s == '':

                if s == '' and i == len(segments) - 1:
                    continue
                return False
        return True

    def get_file_tree(self) -> List[Dict[str, Any]]:
        """
        Build a recursive workspace file tree for the frontend sidebar.

        Generates a tree from:
        - workspace_files (anylegal.md at various levels, Playbook/* files)
        - documents (with full paths including folder hierarchy)
        - folders (explicitly created empty folders)
        - Skills/ (read-only, from disk)

        Returns:
            List of tree nodes. Each node has: name, path, type (file|folder),
            children (for folders), editable (bool), format (for files).
        """

        tree_root: Dict[str, Any] = {"__children": {}, "__files": []}

        def ensure_path(folder_path: str) -> Dict[str, Any]:
            """Ensure all intermediate folders exist in the tree dict."""
            parts = folder_path.replace("\\", "/").strip("/").split("/")
            node = tree_root
            for part in parts:
                if not part:
                    continue
                if part not in node["__children"]:
                    node["__children"][part] = {"__children": {}, "__files": []}
                node = node["__children"][part]
            return node

        for folder_path in self.folders:
            ensure_path(folder_path)

        for path, doc in self.documents.items():
            norm_path = path.replace("\\", "/")
            parts = norm_path.split("/")
            if len(parts) > 1:
                folder = "/".join(parts[:-1])
                node = ensure_path(folder)
            else:
                node = tree_root

            mime_type = doc.mime_type
            if not mime_type:
                lower = norm_path.lower()
                if lower.endswith(('.md', '.markdown')):
                    mime_type = 'text/markdown'
                elif lower.endswith('.txt'):
                    mime_type = 'text/plain'
            node["__files"].append({
                "name": parts[-1],
                "description": doc.description or "",
                "path": path,
                "type": "file",
                "editable": doc.format in ("html", "docx", "markdown"),
                "format": doc.format,
                "has_docx": doc.docx_blob is not None,
                "is_active": path == self.active_document,
                "modified_at": doc.modified_at.isoformat(),
                "mime_type": mime_type,
            })

        for wf_path, wf_content in self.workspace_files.items():
            if wf_path.endswith("anylegal.md"):
                continue                                                          
            parts = wf_path.replace("\\", "/").split("/")
            if len(parts) > 1:
                folder = "/".join(parts[:-1])
                node = ensure_path(folder)
            else:
                node = tree_root

            display_name = parts[-1]
            if wf_path.startswith("Playbook/") and wf_content:
                for line in wf_content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("# "):
                        display_name = stripped[2:].strip()
                        break
            node["__files"].append({
                "name": display_name,
                "path": wf_path,
                "type": "file",
                "editable": True,
                "format": "markdown",
                "has_content": bool(wf_content),
            })

        for system_folder in ("Playbook", "Templates"):
            if system_folder not in tree_root["__children"]:
                ensure_path(system_folder)

        def count_files(node: Dict[str, Any]) -> int:
            count = len(node["__files"])
            for child in node["__children"].values():
                count += count_files(child)
            return count

        def build_tree_nodes(node: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
            result: List[Dict[str, Any]] = []
            is_root = prefix == ""

            if is_root:
                anylegal_key = "anylegal.md"
                anylegal_content = self.workspace_files.get(anylegal_key)
                result.append({
                    "name": "Instructions",
                    "path": anylegal_key,
                    "type": "file",
                    "editable": True,
                    "format": "markdown",
                    "has_content": bool(anylegal_content and anylegal_content.strip()),
                    "is_anylegal": True,
                })

            for file_node in sorted(node["__files"], key=lambda f: f.get("name", "")):
                result.append(file_node)

            COLLAPSED_FOLDERS = {"Playbook", "Templates"}
            SYSTEM_FOLDERS = {"Playbook", "Templates"}
            sorted_folders = sorted(node["__children"].keys())
            if is_root:
                sorted_folders = (
                    [f for f in sorted_folders if f not in SYSTEM_FOLDERS]
                    + [f for f in sorted_folders if f in SYSTEM_FOLDERS]
                )
            for folder_name in sorted_folders:
                child = node["__children"][folder_name]
                child_prefix = f"{prefix}{folder_name}/"
                children = build_tree_nodes(child, child_prefix)
                child_anylegal_key = f"{child_prefix}anylegal.md"

                folder_node: Dict[str, Any] = {
                    "name": folder_name,
                    "path": child_prefix,
                    "type": "folder",
                    "children": children,
                    "count": count_files(child),
                    "has_anylegal": child_anylegal_key in self.workspace_files,
                }
                if is_root and folder_name in COLLAPSED_FOLDERS:
                    folder_node["collapsed"] = True
                if is_root and folder_name in self.NO_INSTRUCTIONS_FOLDERS:
                    folder_node["no_instructions"] = True
                result.append(folder_node)

            return result

        tree = build_tree_nodes(tree_root)

        skill_children = self._get_skill_entries()
        tree.append({
            "name": "Skills",
            "path": "Skills/",
            "type": "folder",
            "children": skill_children,
            "count": len(skill_children),
            "readonly": True,
            "collapsed": True,
        })

        return tree

    def _get_skill_entries(self) -> List[Dict[str, Any]]:
        """Load available skill names from the skills directory."""
        import os
        skills_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "skills"
        )
        entries = []
        if os.path.isdir(skills_dir):
            for name in sorted(os.listdir(skills_dir)):
                skill_path = os.path.join(skills_dir, name)
                if os.path.isdir(skill_path) and os.path.exists(os.path.join(skill_path, "SKILL.md")):
                    entries.append({
                        "name": name,
                        "path": f"Skills/{name}/SKILL.md",
                        "type": "file",
                        "editable": False,
                        "format": "markdown",
                    })
        return entries

    def get_skill_files(self) -> List[Dict[str, Any]]:
        """List skill files for tool responses (path + size)."""
        import os
        skills_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "skills"
        )
        results = []
        if os.path.isdir(skills_dir):
            for name in sorted(os.listdir(skills_dir)):
                skill_path = os.path.join(skills_dir, name, "SKILL.md")
                if os.path.isfile(skill_path):
                    try:
                        size = os.path.getsize(skill_path)
                    except OSError:
                        size = 0
                    results.append({
                        "path": f"Skills/{name}/SKILL.md",
                        "type": "skill",
                        "size": size,
                        "editable": False,
                    })
        return results

    def read_skill_file(self, path: str) -> Optional[str]:
        """Read a skill file from disk. Path format: Skills/<name>/SKILL.md"""
        import os

        parts = path.replace("\\", "/").split("/")
        if len(parts) != 3 or parts[0] != "Skills" or parts[2] != "SKILL.md":
            return None
        skill_name = parts[1]
        disk_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "skills", skill_name, "SKILL.md"
        )
        try:
            with open(disk_path, "r", encoding="utf-8") as f:
                return f.read()
        except (FileNotFoundError, OSError):
            return None

    def get_template_files(self) -> List[Dict[str, Any]]:
        """List template files from session (user-uploaded to Templates/)."""
        results = []
        for path, doc in sorted(self.documents.items()):
            if path.startswith("Templates/"):
                results.append({
                    "path": path,
                    "type": "template",
                    "size": len(doc.content) if doc.content else 0,
                    "format": "docx" if doc.docx_blob else doc.format,
                    "editable": False,
                })
        return results

    def to_dict(self, include_docx: bool = False) -> Dict[str, Any]:
        """
        Serialize session to dictionary.

        Args:
            include_docx: If True, include base64-encoded DOCX blobs (for API responses)
        """
        import base64

        documents_data = {}
        for path, doc in self.documents.items():
            doc_data = {
                "content": doc.content,
                "description": doc.description,
                "created_at": doc.created_at.isoformat(),
                "modified_at": doc.modified_at.isoformat(),
                "format": doc.format,
                "is_synced": doc.is_synced,
                "has_docx": doc.docx_blob is not None,
                "has_binary": doc.binary_blob is not None,
                "mime_type": doc.mime_type,
            }
            if include_docx and doc.docx_blob is not None:
                doc_data["docx_blob_b64"] = base64.b64encode(doc.docx_blob).decode('utf-8')
            documents_data[path] = doc_data

        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "documents": documents_data,
            "active_document": self.active_document,
            "playbook": self.playbook,
            "agents_md": self.agents_md,
            "workspace_files": self.workspace_files,
            "folders": sorted(self.folders),
            "context": self.context,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], docx_blobs: Optional[Dict[str, bytes]] = None) -> "WorkspaceSession":
        """
        Deserialize session from dictionary (used for API responses).

        Args:
            data: Session data dictionary
            docx_blobs: Optional dict mapping document paths to binary bytes
        """
        import base64

        session = cls(
            user_id=data["user_id"],
            session_id=data.get("session_id"),
            playbook=data.get("playbook")
        )
        session.context = data.get("context", {})
        session.active_document = data.get("active_document")
        session.folders = set(data.get("folders", []))

        session.workspace_files = data.get("workspace_files", {})
        agents_md_val = data.get("agents_md")
        if agents_md_val and "anylegal.md" not in session.workspace_files:
            session.workspace_files["anylegal.md"] = agents_md_val

        stale_keys = [
            k for k in session.workspace_files
            if k.endswith("/anylegal.md") and k.split("/")[0] in cls.NO_INSTRUCTIONS_FOLDERS
        ]
        for k in stale_keys:
            del session.workspace_files[k]

        has_any_playbook_file = any(
            k.startswith("Playbook/") and k.endswith(".md")
            and not k.endswith("/anylegal.md")
            for k in session.workspace_files
        )
        if session.playbook and not has_any_playbook_file:
            session.workspace_files["Playbook/positions.md"] = session.playbook
            session.folders.add("Playbook/")

        all_blobs = docx_blobs or {}

        for path, doc_data in data.get("documents", {}).items():

            blob = None
            if "docx_blob_b64" in doc_data:
                blob = base64.b64decode(doc_data["docx_blob_b64"])
            elif path in all_blobs:
                blob = all_blobs[path]

            doc_format = doc_data.get("format", "html")
            docx_blob = None
            binary_blob = None
            if blob:
                if doc_format == "docx" or doc_data.get("has_docx"):
                    docx_blob = blob
                elif doc_data.get("has_binary"):
                    binary_blob = blob

            session.documents[path] = DocumentMeta(
                content=doc_data.get("content", ""),
                description=doc_data.get("description", ""),
                created_at=datetime.fromisoformat(doc_data["created_at"]) if "created_at" in doc_data else datetime.now(timezone.utc),
                modified_at=datetime.fromisoformat(doc_data["modified_at"]) if "modified_at" in doc_data else datetime.now(timezone.utc),
                docx_blob=docx_blob,
                binary_blob=binary_blob,
                mime_type=doc_data.get("mime_type"),
                format=doc_format,
                is_synced=doc_data.get("is_synced", True)
            )

        return session

    def save(self, session_name: Optional[str] = None) -> bool:
        """
        Persist the workspace session to the database with encryption.

        Args:
            session_name: Optional human-readable name for the session

        Returns:
            True if saved successfully
        """
        from anylegal_oss.workspace.db import save_workspace_session

        documents_data = {
            path: {
                "content": doc.content,
                "description": doc.description,
                "created_at": doc.created_at.isoformat(),
                "modified_at": doc.modified_at.isoformat(),
                "format": doc.format,
                "is_synced": doc.is_synced,
                "has_docx": doc.docx_blob is not None,
                "has_binary": doc.binary_blob is not None,
                "mime_type": doc.mime_type,
            }
            for path, doc in self.documents.items()
        }

        all_blobs = {}
        for path, doc in self.documents.items():
            if doc.docx_blob is not None:
                all_blobs[path] = doc.docx_blob
            elif doc.binary_blob is not None:
                all_blobs[path] = doc.binary_blob

        extended_context = {
            **(self.context or {}),
            "__workspace_files": self.workspace_files,
            "__folders": sorted(self.folders),
        }

        return save_workspace_session(
            session_id=self.session_id,
            user_id=self.user_id,
            documents=documents_data,
            active_document=self.active_document,
            session_name=session_name or self._generate_session_name(),
            playbook=self.playbook,
            context_data=extended_context,
            docx_blobs=all_blobs
        )

    def _generate_session_name(self) -> str:
        """Generate a session name from the active document or timestamp."""
        if self.active_document:

            name = self.active_document.rsplit('.', 1)[0]
            return f"Review: {name}"
        return f"Session {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    @classmethod
    def load(cls, session_id: str, user_id: int) -> Optional["WorkspaceSession"]:
        """
        Load a workspace session from the database.

        Extracts workspace_files and folders from context_data (packed there
        by save()). Falls back to legacy top-level fields for old sessions.

        Args:
            session_id: Session identifier
            user_id: User ID (for access control)

        Returns:
            WorkspaceSession instance or None if not found
        """
        from anylegal_oss.workspace.db import load_workspace_session

        data = load_workspace_session(session_id, user_id)
        if not data:
            return None

        if 'playbook' in data:
            stored_playbook = data['playbook']                                     
        else:
            stored_playbook = cls._UNSET                                
        session = cls(
            user_id=user_id,
            session_id=session_id,
            playbook=stored_playbook
        )
        session.active_document = data.get('active_document')

        raw_context = dict(data.get('context', {}))
        session.workspace_files = raw_context.pop("__workspace_files", {})
        session.folders = set(raw_context.pop("__folders", []))
        session.context = raw_context

        legacy_agents = data.get('agents_md')
        if legacy_agents and "anylegal.md" not in session.workspace_files:
            session.workspace_files["anylegal.md"] = legacy_agents

        legacy_wf = data.get('workspace_files')
        if legacy_wf and isinstance(legacy_wf, dict):
            for k, v in legacy_wf.items():
                if k not in session.workspace_files:
                    session.workspace_files[k] = v

        stale_keys = [
            k for k in session.workspace_files
            if k.endswith("/anylegal.md") and k.split("/")[0] in cls.NO_INSTRUCTIONS_FOLDERS
        ]
        for k in stale_keys:
            del session.workspace_files[k]

        has_any_playbook_file = any(
            k.startswith("Playbook/") and k.endswith(".md")
            and not k.endswith("/anylegal.md")
            for k in session.workspace_files
        )
        if session.playbook and not has_any_playbook_file:
            session.workspace_files["Playbook/positions.md"] = session.playbook
            session.folders.add("Playbook/")

        all_blobs = data.get('docx_blobs', {})

        for path, doc_data in data.get('documents', {}).items():
            blob = all_blobs.get(path) if all_blobs else None
            doc_format = doc_data.get('format', 'html')

            docx_blob = None
            binary_blob = None
            if blob:
                if doc_format == 'docx' or doc_data.get('has_docx'):
                    docx_blob = blob
                elif doc_data.get('has_binary'):
                    binary_blob = blob

            session.documents[path] = DocumentMeta(
                content=doc_data.get('content', ''),
                description=doc_data.get('description', ''),
                created_at=datetime.fromisoformat(doc_data['created_at']) if 'created_at' in doc_data else datetime.now(timezone.utc),
                modified_at=datetime.fromisoformat(doc_data['modified_at']) if 'modified_at' in doc_data else datetime.now(timezone.utc),
                docx_blob=docx_blob,
                binary_blob=binary_blob,
                mime_type=doc_data.get('mime_type'),
                format=doc_format,
                is_synced=doc_data.get('is_synced', True)
            )

        return session

    @staticmethod
    def list_sessions(user_id: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List workspace sessions for a user.

        Args:
            user_id: User ID
            status: Optional filter by status ('active', 'archived')

        Returns:
            List of session metadata
        """
        from anylegal_oss.workspace.db import list_workspace_sessions
        return list_workspace_sessions(user_id, status)

    def delete(self) -> bool:
        """
        Delete this workspace session from the database.

        Returns:
            True if deleted successfully
        """
        from anylegal_oss.workspace.db import delete_workspace_session
        return delete_workspace_session(self.session_id, self.user_id)
