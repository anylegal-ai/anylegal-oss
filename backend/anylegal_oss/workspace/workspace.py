"""
Workspace — Persistent per-user workspace.

Extends WorkspaceSession with persistent storage in the `workspaces` table.
One workspace per user. Documents, folders, playbook, and instructions survive
across chat sessions.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from .session import WorkspaceSession, DocumentMeta

logger = logging.getLogger(__name__)

class Workspace(WorkspaceSession):
    """
    Persistent user workspace. One per user.

    Inherits all document/folder/playbook management from WorkspaceSession.
    Overrides save/load to use the `workspaces` table instead of
    `document_sessions`.
    """

    def __init__(
        self,
        user_id: int,
        workspace_id: Optional[str] = None,
        playbook: Any = WorkspaceSession._UNSET,
    ):

        super().__init__(
            user_id=user_id,
            session_id=workspace_id or str(uuid.uuid4()),
            playbook=playbook,
        )

    @property
    def workspace_id(self) -> str:
        """Alias for session_id — the workspace's unique identifier."""
        return self.session_id

    @workspace_id.setter
    def workspace_id(self, value: str):
        self.session_id = value

    def save(self, session_name: Optional[str] = None) -> bool:
        """Persist workspace to the workspaces table (encrypted)."""
        from .db import save_workspace

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

        return save_workspace(
            workspace_id=self.workspace_id,
            user_id=self.user_id,
            documents=documents_data,
            active_document=self.active_document,
            playbook=self.playbook,
            context_data=extended_context,
            docx_blobs=all_blobs,
        )

    @classmethod
    def load(cls, user_id: int, **_kwargs) -> Optional["Workspace"]:
        """
        Load the persistent workspace for a user.

        Returns None if no workspace exists yet.
        """
        from .db import load_workspace_by_user

        data = load_workspace_by_user(user_id)
        if not data:
            return None

        workspace_id = data['id']

        if 'playbook' in data:
            stored_playbook = data['playbook']
        else:
            stored_playbook = cls._UNSET

        ws = cls(
            user_id=user_id,
            workspace_id=workspace_id,
            playbook=stored_playbook,
        )
        ws.active_document = data.get('active_document')

        raw_context = dict(data.get('context', {}))
        ws.workspace_files = raw_context.pop("__workspace_files", {})
        ws.folders = set(raw_context.pop("__folders", []))
        ws.context = raw_context

        legacy_agents = data.get('agents_md')
        if legacy_agents and "anylegal.md" not in ws.workspace_files:
            ws.workspace_files["anylegal.md"] = legacy_agents

        stale_keys = [
            k for k in ws.workspace_files
            if k.endswith("/anylegal.md") and k.split("/")[0] in cls.NO_INSTRUCTIONS_FOLDERS
        ]
        for k in stale_keys:
            del ws.workspace_files[k]

        has_any_playbook_file = any(
            k.startswith("Playbook/") and k.endswith(".md")
            and not k.endswith("/anylegal.md")
            for k in ws.workspace_files
        )
        if ws.playbook and not has_any_playbook_file:
            ws.workspace_files["Playbook/positions.md"] = ws.playbook
            ws.folders.add("Playbook/")

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

            ws.documents[path] = DocumentMeta(
                content=doc_data.get('content', ''),
                description=doc_data.get('description', ''),
                created_at=(
                    datetime.fromisoformat(doc_data['created_at'])
                    if 'created_at' in doc_data
                    else datetime.now(timezone.utc)
                ),
                modified_at=(
                    datetime.fromisoformat(doc_data['modified_at'])
                    if 'modified_at' in doc_data
                    else datetime.now(timezone.utc)
                ),
                docx_blob=docx_blob,
                binary_blob=binary_blob,
                mime_type=doc_data.get('mime_type'),
                format=doc_format,
                is_synced=doc_data.get('is_synced', True),
            )

        return ws

    @classmethod
    def get_or_create(cls, user_id: int) -> "Workspace":
        """
        Load existing workspace or create a new one for the user.

        New workspaces are auto-seeded with the default playbook.
        """
        ws = cls.load(user_id)
        if ws is None:
            ws = cls(user_id=user_id)
            ws.save()
            logger.info(
                f"Created new workspace {ws.workspace_id} for user {user_id}"
            )
        return ws

    def delete(self) -> bool:
        """Delete this workspace from the database."""
        from .db import delete_workspace
        return delete_workspace(self.workspace_id, self.user_id)
