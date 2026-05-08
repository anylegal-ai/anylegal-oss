"""Database helpers for the LexWiki workspace knowledge base.

Lives outside `anylegal_oss.workspace.db` because the compiler container
imports this module without wanting to drag in the workspace package's
Flask-heavy `__init__`. Backend API code (api.py) imports from here too,
so all wiki SQL is in one place.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from anylegal_oss.db.database import get_db_connection
from anylegal_oss.utils.encryption import (
    decrypt_bytes,
    decrypt_text,
    encrypt_bytes,
    ENCRYPTION_AVAILABLE,
)

logger = logging.getLogger(__name__)

def migrate_create_workspace_wikis_table() -> None:
    """Create workspace_wikis table. Idempotent — safe to call on every startup."""
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS workspace_wikis (
                workspace_id TEXT PRIMARY KEY,
                wiki_data BLOB,
                source_doc_count INTEGER DEFAULT 0,
                source_docs_hash TEXT,
                compiled_at DATETIME,
                compile_status TEXT DEFAULT 'pending',
                compile_error TEXT,
                last_compile_cost_usd REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
            )
        ''')
        conn.execute(
            'CREATE INDEX IF NOT EXISTS idx_workspace_wikis_status '
            'ON workspace_wikis(compile_status)'
        )
        conn.commit()
        logger.info("workspace_wikis table migration complete")

def get_workspace_wiki(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Read the compiled wiki for a workspace.

    Returns the row with `wiki_data` decrypted into a dict, or None if no
    row exists. When wiki_data is populated, its shape is:

        {
            "pages": {slug: {"category", "frontmatter", "content"}},
            "indexes": {"clause_library", "by_party", "by_jurisdiction", ...},
            "findings": [LintIssue dicts],
        }
    """
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT workspace_id, wiki_data, source_doc_count, source_docs_hash, "
            "compiled_at, compile_status, compile_error, last_compile_cost_usd "
            "FROM workspace_wikis WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()

    if not row:
        return None

    wiki_data: Optional[Dict[str, Any]] = None
    if row['wiki_data']:
        try:
            decrypted = decrypt_bytes(row['wiki_data']) if ENCRYPTION_AVAILABLE else row['wiki_data']
            wiki_data = json.loads(decrypted.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to decrypt/parse wiki_data for {workspace_id}: {e}")
            wiki_data = None

    return {
        "workspace_id": row['workspace_id'],
        "wiki_data": wiki_data,
        "source_doc_count": row['source_doc_count'],
        "source_docs_hash": row['source_docs_hash'],
        "compiled_at": row['compiled_at'],
        "compile_status": row['compile_status'],
        "compile_error": row['compile_error'],
        "last_compile_cost_usd": row['last_compile_cost_usd'],
    }

def get_workspace_for_compile(workspace_id: str) -> Optional[Dict[str, Any]]:
    """Read the encrypted workspace blob and decrypt it for compilation."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT id, user_id, workspace_documents, docx_blobs, updated_at "
            "FROM workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()

    if not row:
        return None

    documents: Dict[str, Any] = {}
    if row['workspace_documents']:
        try:
            decrypted = decrypt_text(row['workspace_documents']) if ENCRYPTION_AVAILABLE else row['workspace_documents']
            documents = json.loads(decrypted) if decrypted else {}
        except Exception as e:
            logger.error(f"Failed to decrypt documents for {workspace_id}: {e}")

    docx_blobs: Dict[str, bytes] = {}
    if row['docx_blobs']:
        try:
            blobs_data = json.loads(row['docx_blobs'])
            for path, b64 in blobs_data.items():
                raw = base64.b64decode(b64)
                docx_blobs[path] = decrypt_bytes(raw) if ENCRYPTION_AVAILABLE else raw
        except Exception as e:
            logger.error(f"Failed to decrypt docx_blobs for {workspace_id}: {e}")

    return {
        "id": row['id'],
        "user_id": row['user_id'],
        "documents": documents,
        "docx_blobs": docx_blobs,
        "updated_at": row['updated_at'],
    }

STALE_COMPILE_MINUTES = 15

def find_workspaces_needing_recompile(debounce_seconds: int = 300) -> List[str]:
    """Return workspace IDs the user has explicitly queued for recompile.

    Pivot from auto-detect: we no longer compare workspaces.updated_at vs
    workspace_wikis.compiled_at — that triggered a full re-extraction every
    time the user (or the agent) edited any doc, which is wasteful since the
    agent maintains the wiki incrementally via the edit-wiki tools (append_
    wiki_note, set_wiki_metadata, etc.).

    Compile is now bootstrap-only: it fires when (a) the user clicks the
    Recompile button (which sets compile_status='pending'), or (b) a
    workspace has no wiki row at all (initial bootstrap on first compile
    request). Stale-compile recovery still applies: rows stuck in
    'compiling' for longer than STALE_COMPILE_MINUTES are re-picked up.

    The `debounce_seconds` argument is kept for signature compatibility but
    no longer applies — explicit pending state is its own gate.
    """
    _ = debounce_seconds                             
    with get_db_connection() as conn:
        rows = conn.execute(f'''
            SELECT w.id
            FROM workspaces w
            LEFT JOIN workspace_wikis ww ON w.id = ww.workspace_id
            WHERE
                ww.workspace_id IS NULL
                OR ww.compile_status = 'pending'
                OR (ww.compile_status = 'compiling'
                    AND ww.updated_at < datetime('now', '-{STALE_COMPILE_MINUTES} minutes'))
            ORDER BY w.updated_at ASC
        ''').fetchall()
    return [row['id'] for row in rows]

def auto_expire_stale_compiling(workspace_id: str) -> bool:
    """If this workspace's wiki has been 'compiling' for too long, flip it to
    'error' with a stale-compile note. Called from the status read path so
    the UI doesn't perpetually show "compiling" when the compiler died.

    Returns True if the row was rewritten.
    """
    with get_db_connection() as conn:
        row = conn.execute(
            f"SELECT compile_status FROM workspace_wikis "
            f"WHERE workspace_id = ? AND compile_status = 'compiling' "
            f"AND updated_at < datetime('now', '-{STALE_COMPILE_MINUTES} minutes')",
            (workspace_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE workspace_wikis SET compile_status = 'error', "
            "compile_error = ?, updated_at = ? WHERE workspace_id = ?",
            (
                f"compile job did not complete within {STALE_COMPILE_MINUTES} minutes — likely killed",
                datetime.now().isoformat(),
                workspace_id,
            ),
        )
        conn.commit()
    return True

def update_workspace_wiki(
    workspace_id: str,
    wiki_data: Dict[str, Any],
    source_doc_count: int,
    source_docs_hash: str,
    cost_usd: Optional[float] = None,
) -> bool:
    """Persist a freshly compiled wiki. Encrypts wiki_data, sets status='ready'."""
    try:

        payload = json.dumps(wiki_data, default=str).encode('utf-8')
        encrypted = encrypt_bytes(payload) if ENCRYPTION_AVAILABLE else payload
        now = datetime.now().isoformat()

        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT workspace_id FROM workspace_wikis WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()

            if existing:
                conn.execute('''
                    UPDATE workspace_wikis SET
                        wiki_data = ?,
                        source_doc_count = ?,
                        source_docs_hash = ?,
                        compiled_at = ?,
                        compile_status = 'ready',
                        compile_error = NULL,
                        last_compile_cost_usd = ?,
                        updated_at = ?
                    WHERE workspace_id = ?
                ''', (encrypted, source_doc_count, source_docs_hash, now, cost_usd, now, workspace_id))
            else:
                conn.execute('''
                    INSERT INTO workspace_wikis
                    (workspace_id, wiki_data, source_doc_count, source_docs_hash,
                     compiled_at, compile_status, last_compile_cost_usd,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 'ready', ?, ?, ?)
                ''', (workspace_id, encrypted, source_doc_count, source_docs_hash,
                      now, cost_usd, now, now))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update wiki for workspace {workspace_id}: {e}")
        return False

def update_workspace_wiki_status(
    workspace_id: str,
    status: str,
    error: Optional[str] = None,
) -> bool:
    """Transition compile_status without touching wiki_data."""
    if status not in ('pending', 'compiling', 'ready', 'error'):
        logger.warning(f"Invalid wiki status: {status}")
        return False
    try:
        now = datetime.now().isoformat()
        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT workspace_id FROM workspace_wikis WHERE workspace_id = ?",
                (workspace_id,),
            ).fetchone()
            if existing:
                conn.execute('''
                    UPDATE workspace_wikis SET
                        compile_status = ?,
                        compile_error = ?,
                        updated_at = ?
                    WHERE workspace_id = ?
                ''', (status, error, now, workspace_id))
            else:
                conn.execute('''
                    INSERT INTO workspace_wikis
                    (workspace_id, compile_status, compile_error, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                ''', (workspace_id, status, error, now, now))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to update wiki status for {workspace_id}: {e}")
        return False
