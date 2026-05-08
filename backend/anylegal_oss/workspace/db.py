"""
Database functions for the Document Editor module.

Manages playbook clauses, rules, and session data using the existing
Anylegal SQLite infrastructure.
"""

import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from anylegal_oss.db.database import get_db_connection
from anylegal_oss.utils.encryption import encrypt_text, decrypt_text, ENCRYPTION_AVAILABLE

logger = logging.getLogger(__name__)

def init_document_editor_tables():
    """
    Initialize document editor tables in the existing database.

    Should be called during application startup.
    """
    with get_db_connection() as conn:
        conn.executescript('''
        -- ============================================
        -- PLAYBOOK TABLES
        -- ============================================

        -- Clause library: Preferred language for contract provisions
        CREATE TABLE IF NOT EXISTS playbook_clauses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),

            -- Categorization
            clause_type TEXT NOT NULL,
            position TEXT NOT NULL,

            -- Content
            title TEXT NOT NULL,
            clause_text TEXT NOT NULL,
            explanation TEXT,

            -- Metadata
            jurisdiction TEXT DEFAULT 'GENERAL',
            contract_type TEXT,
            tags TEXT,  -- JSON array as string

            -- Tracking
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0
        );

        -- Redline rules: Automatic redline decisions
        CREATE TABLE IF NOT EXISTS playbook_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),

            -- Rule definition
            name TEXT NOT NULL,
            description TEXT,
            rule_type TEXT NOT NULL,

            -- Trigger conditions
            trigger_clause_type TEXT,
            trigger_keywords TEXT,  -- JSON array as string
            trigger_semantic TEXT,

            -- Action
            action TEXT NOT NULL,  -- JSON object as string
            severity TEXT DEFAULT 'medium',

            -- Scope
            contract_types TEXT,  -- JSON array as string
            jurisdictions TEXT,   -- JSON array as string

            -- Tracking
            priority INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ============================================
        -- SESSION TABLES (for future use)
        -- ============================================

        -- Active editing sessions
        CREATE TABLE IF NOT EXISTS document_sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),

            -- Document info
            document_name TEXT NOT NULL,
            document_type TEXT,

            -- State
            original_content TEXT,
            current_content TEXT,

            -- Metadata
            detected_clauses TEXT,  -- JSON
            detected_parties TEXT,  -- JSON

            -- Tracking
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'active'
        );

        -- Redline history within a session
        CREATE TABLE IF NOT EXISTS redline_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES document_sessions(id),

            -- Change details
            change_type TEXT NOT NULL,
            original_text TEXT,
            new_text TEXT,

            -- Location
            start_offset INTEGER,
            end_offset INTEGER,
            clause_type TEXT,

            -- Source
            source TEXT NOT NULL,
            rule_id INTEGER REFERENCES playbook_rules(id),

            -- Decision
            status TEXT DEFAULT 'pending',
            user_comment TEXT,

            -- Tracking
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME
        );

        -- ============================================
        -- TEMPLATE TABLES
        -- ============================================

        -- Document templates for generating new documents
        CREATE TABLE IF NOT EXISTS document_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),

            -- Basic info
            name TEXT NOT NULL,
            description TEXT,
            template_type TEXT NOT NULL,  -- nda, spa, employment, etc.

            -- Content
            content TEXT NOT NULL,
            variables TEXT,  -- JSON array of placeholders

            -- Metadata
            jurisdiction TEXT DEFAULT 'GENERAL',

            -- Tracking
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0
        );

        -- Context templates for review presets
        CREATE TABLE IF NOT EXISTS context_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER REFERENCES users(id),

            -- Basic info
            name TEXT NOT NULL,
            description TEXT,

            -- Content
            context_text TEXT NOT NULL,
            document_types TEXT,  -- JSON array

            -- Flags
            is_default INTEGER DEFAULT 0,

            -- Tracking
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        -- ============================================
        -- INDEXES
        -- ============================================

        CREATE INDEX IF NOT EXISTS idx_playbook_clauses_type 
            ON playbook_clauses(clause_type, position);
        CREATE INDEX IF NOT EXISTS idx_playbook_clauses_user 
            ON playbook_clauses(user_id);
        CREATE INDEX IF NOT EXISTS idx_playbook_rules_user 
            ON playbook_rules(user_id);
        CREATE INDEX IF NOT EXISTS idx_playbook_rules_type 
            ON playbook_rules(trigger_clause_type);
        CREATE INDEX IF NOT EXISTS idx_document_sessions_user 
            ON document_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_redline_history_session 
            ON redline_history(session_id);
        CREATE INDEX IF NOT EXISTS idx_document_templates_user 
            ON document_templates(user_id);
        CREATE INDEX IF NOT EXISTS idx_context_templates_user 
            ON context_templates(user_id);
        ''')
        conn.commit()
        logger.info("Document editor tables initialized successfully")

def migrate_document_sessions_table():
    """
    Add encrypted workspace documents support to document_sessions table.

    Adds columns:
    - workspace_documents: JSON blob containing encrypted document data
    - is_encrypted: Flag indicating if content is encrypted
    - session_name: Human-readable session name
    - docx_blobs: Encrypted BLOB storage for native DOCX files (Hybrid Architecture)
    """
    with get_db_connection() as conn:

        cursor = conn.execute("PRAGMA table_info(document_sessions)")
        existing_columns = {row['name'] for row in cursor.fetchall()}

        migrations = []

        if 'workspace_documents' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN workspace_documents TEXT"
            )

        if 'is_encrypted' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN is_encrypted INTEGER DEFAULT 1"
            )

        if 'session_name' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN session_name TEXT"
            )

        if 'playbook' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN playbook TEXT"
            )

        if 'context_data' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN context_data TEXT"
            )

        if 'docx_blobs' not in existing_columns:
            migrations.append(
                "ALTER TABLE document_sessions ADD COLUMN docx_blobs BLOB"
            )

        for migration in migrations:
            try:
                conn.execute(migration)
                logger.info(f"Migration applied: {migration[:50]}...")
            except Exception as e:

                logger.debug(f"Migration skipped (may already exist): {e}")

        conn.commit()

        if migrations:
            logger.info(f"Applied {len(migrations)} migrations to document_sessions table")

def create_playbook_clause(
    user_id: int,
    clause_type: str,
    position: str,
    title: str,
    clause_text: str,
    explanation: Optional[str] = None,
    jurisdiction: str = "GENERAL",
    contract_type: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> int:
    """Create a new playbook clause."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO playbook_clauses 
            (user_id, clause_type, position, title, clause_text, explanation, 
             jurisdiction, contract_type, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, clause_type, position, title, clause_text, explanation,
            jurisdiction, contract_type, json.dumps(tags or [])
        ))
        conn.commit()
        return cursor.lastrowid

def get_playbook_clauses(
    user_id: int,
    clause_type: Optional[str] = None,
    position: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    contract_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get playbook clauses with optional filtering."""
    with get_db_connection() as conn:
        query = "SELECT * FROM playbook_clauses WHERE user_id = ?"
        params = [user_id]

        if clause_type:
            query += " AND clause_type = ?"
            params.append(clause_type)
        if position:
            query += " AND position = ?"
            params.append(position)
        if jurisdiction:
            query += " AND jurisdiction = ?"
            params.append(jurisdiction)
        if contract_type:
            query += " AND contract_type = ?"
            params.append(contract_type)

        query += " ORDER BY usage_count DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        clauses = []
        for row in rows:
            clause = dict(row)

            clause['tags'] = json.loads(clause.get('tags') or '[]')
            clauses.append(clause)

        return clauses

def get_playbook_clause_by_id(clause_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific playbook clause by ID."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM playbook_clauses WHERE id = ? AND user_id = ?",
            (clause_id, user_id)
        ).fetchone()

        if row:
            clause = dict(row)
            clause['tags'] = json.loads(clause.get('tags') or '[]')
            return clause
        return None

def update_playbook_clause(
    clause_id: int,
    user_id: int,
    **updates
) -> bool:
    """Update a playbook clause."""
    allowed_fields = {
        'clause_type', 'position', 'title', 'clause_text', 'explanation',
        'jurisdiction', 'contract_type', 'tags'
    }

    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        return False

    if 'tags' in valid_updates:
        valid_updates['tags'] = json.dumps(valid_updates['tags'])

    set_clause = ", ".join(f"{k} = ?" for k in valid_updates.keys())
    set_clause += ", updated_at = CURRENT_TIMESTAMP"

    with get_db_connection() as conn:
        conn.execute(
            f"UPDATE playbook_clauses SET {set_clause} WHERE id = ? AND user_id = ?",
            list(valid_updates.values()) + [clause_id, user_id]
        )
        conn.commit()
        return True

def delete_playbook_clause(clause_id: int, user_id: int) -> bool:
    """Delete a playbook clause."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM playbook_clauses WHERE id = ? AND user_id = ?",
            (clause_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def increment_clause_usage(clause_id: int) -> None:
    """Increment the usage count for a clause."""
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE playbook_clauses SET usage_count = usage_count + 1 WHERE id = ?",
            (clause_id,)
        )
        conn.commit()

def create_playbook_rule(
    user_id: int,
    name: str,
    rule_type: str,
    action: dict,
    description: Optional[str] = None,
    trigger_clause_type: Optional[str] = None,
    trigger_keywords: Optional[List[str]] = None,
    trigger_semantic: Optional[str] = None,
    severity: str = "medium",
    priority: int = 0,
    contract_types: Optional[List[str]] = None,
    jurisdictions: Optional[List[str]] = None
) -> int:
    """Create a new playbook rule."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO playbook_rules 
            (user_id, name, description, rule_type, trigger_clause_type,
             trigger_keywords, trigger_semantic, action, severity, priority,
             contract_types, jurisdictions)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id, name, description, rule_type, trigger_clause_type,
            json.dumps(trigger_keywords or []),
            trigger_semantic,
            json.dumps(action),
            severity, priority,
            json.dumps(contract_types) if contract_types else None,
            json.dumps(jurisdictions) if jurisdictions else None
        ))
        conn.commit()
        return cursor.lastrowid

def get_playbook_rules(
    user_id: int,
    rule_type: Optional[str] = None,
    trigger_clause_type: Optional[str] = None,
    is_active: bool = True,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get playbook rules with optional filtering."""
    with get_db_connection() as conn:
        query = "SELECT * FROM playbook_rules WHERE user_id = ?"
        params = [user_id]

        if rule_type:
            query += " AND rule_type = ?"
            params.append(rule_type)
        if trigger_clause_type:
            query += " AND trigger_clause_type = ?"
            params.append(trigger_clause_type)
        if is_active is not None:
            query += " AND is_active = ?"
            params.append(1 if is_active else 0)

        query += " ORDER BY priority DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()

        rules = []
        for row in rows:
            rule = dict(row)

            rule['trigger_keywords'] = json.loads(rule.get('trigger_keywords') or '[]')
            rule['action'] = json.loads(rule.get('action') or '{}')
            rule['contract_types'] = json.loads(rule.get('contract_types') or 'null')
            rule['jurisdictions'] = json.loads(rule.get('jurisdictions') or 'null')
            rule['is_active'] = bool(rule.get('is_active'))
            rules.append(rule)

        return rules

def get_matching_rules(
    user_id: int,
    clause_text: str,
    clause_type: Optional[str] = None,
    contract_type: Optional[str] = None,
    jurisdiction: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Get rules that match given criteria."""

    rules = get_playbook_rules(user_id, is_active=True)

    matching = []
    clause_text_lower = clause_text.lower()

    for rule in rules:

        if rule['trigger_clause_type'] and clause_type:
            if rule['trigger_clause_type'] != clause_type:
                continue

        if rule['trigger_keywords']:
            keywords_matched = any(
                kw.lower() in clause_text_lower 
                for kw in rule['trigger_keywords']
            )
            if not keywords_matched:
                continue

        if rule['contract_types'] and contract_type:
            if contract_type not in rule['contract_types']:
                continue

        if rule['jurisdictions'] and jurisdiction:
            if jurisdiction not in rule['jurisdictions']:
                continue

        matching.append(rule)

    matching.sort(key=lambda r: r.get('priority', 0), reverse=True)

    return matching

def update_playbook_rule(rule_id: int, user_id: int, **updates) -> bool:
    """Update a playbook rule."""
    allowed_fields = {
        'name', 'description', 'rule_type', 'trigger_clause_type',
        'trigger_keywords', 'trigger_semantic', 'action', 'severity',
        'priority', 'is_active', 'contract_types', 'jurisdictions'
    }

    valid_updates = {k: v for k, v in updates.items() if k in allowed_fields}

    if not valid_updates:
        return False

    json_fields = ['trigger_keywords', 'action', 'contract_types', 'jurisdictions']
    for field in json_fields:
        if field in valid_updates:
            valid_updates[field] = json.dumps(valid_updates[field])

    if 'is_active' in valid_updates:
        valid_updates['is_active'] = 1 if valid_updates['is_active'] else 0

    set_clause = ", ".join(f"{k} = ?" for k in valid_updates.keys())

    with get_db_connection() as conn:
        conn.execute(
            f"UPDATE playbook_rules SET {set_clause} WHERE id = ? AND user_id = ?",
            list(valid_updates.values()) + [rule_id, user_id]
        )
        conn.commit()
        return True

def delete_playbook_rule(rule_id: int, user_id: int) -> bool:
    """Delete a playbook rule."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM playbook_rules WHERE id = ? AND user_id = ?",
            (rule_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def create_document_session(
    session_id: str,
    user_id: int,
    document_name: str,
    document_type: Optional[str] = None,
    original_content: Optional[str] = None
) -> str:
    """Create a new document editing session."""
    with get_db_connection() as conn:
        conn.execute('''
            INSERT INTO document_sessions 
            (id, user_id, document_name, document_type, original_content, current_content)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, user_id, document_name, document_type, 
              original_content, original_content))
        conn.commit()
        return session_id

def get_document_session(session_id: str, user_id: int) -> Optional[Dict[str, Any]]:
    """Get a document session."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM document_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id)
        ).fetchone()

        if row:
            session = dict(row)
            session['detected_clauses'] = json.loads(session.get('detected_clauses') or '[]')
            session['detected_parties'] = json.loads(session.get('detected_parties') or '[]')
            return session
        return None

def log_redline_action(
    session_id: str,
    change_type: str,
    source: str,
    original_text: Optional[str] = None,
    new_text: Optional[str] = None,
    clause_type: Optional[str] = None,
    rule_id: Optional[int] = None,
    status: str = "pending"
) -> int:
    """Log a redline action in session history."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO redline_history 
            (session_id, change_type, original_text, new_text, clause_type, 
             source, rule_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, change_type, original_text, new_text, clause_type,
              source, rule_id, status))
        conn.commit()
        return cursor.lastrowid

def create_document_template(
    user_id: int,
    name: str,
    template_type: str,
    content: str,
    description: Optional[str] = None,
    variables: Optional[List[str]] = None,
    jurisdiction: str = "GENERAL"
) -> int:
    """Create a new document template."""
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO document_templates 
            (user_id, name, description, template_type, content, variables, jurisdiction)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, name, description, template_type, content, 
              json.dumps(variables or []), jurisdiction))
        conn.commit()
        return cursor.lastrowid

def get_document_templates(
    user_id: int,
    template_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get user's document templates."""
    with get_db_connection() as conn:
        query = "SELECT * FROM document_templates WHERE user_id = ?"
        params = [user_id]

        if template_type:
            query += " AND template_type = ?"
            params.append(template_type)

        query += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        templates = []
        for row in rows:
            t = dict(row)
            t['variables'] = json.loads(t.get('variables') or '[]')
            templates.append(t)
        return templates

def get_document_template(template_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific document template."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM document_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        ).fetchone()
        if row:
            t = dict(row)
            t['variables'] = json.loads(t.get('variables') or '[]')
            return t
        return None

def update_document_template(
    template_id: int,
    user_id: int,
    **updates
) -> bool:
    """Update a document template."""
    allowed = {'name', 'description', 'template_type', 'content', 'variables', 'jurisdiction'}
    valid_updates = {k: v for k, v in updates.items() if k in allowed and v is not None}

    if not valid_updates:
        return False

    if 'variables' in valid_updates:
        valid_updates['variables'] = json.dumps(valid_updates['variables'])

    valid_updates['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in valid_updates.keys())

    with get_db_connection() as conn:
        conn.execute(
            f"UPDATE document_templates SET {set_clause} WHERE id = ? AND user_id = ?",
            list(valid_updates.values()) + [template_id, user_id]
        )
        conn.commit()
        return True

def delete_document_template(template_id: int, user_id: int) -> bool:
    """Delete a document template."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM document_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def create_context_template(
    user_id: int,
    name: str,
    context_text: str,
    description: Optional[str] = None,
    document_types: Optional[List[str]] = None,
    is_default: bool = False
) -> int:
    """Create a new context template."""
    with get_db_connection() as conn:

        if is_default:
            conn.execute(
                "UPDATE context_templates SET is_default = 0 WHERE user_id = ?",
                (user_id,)
            )

        cursor = conn.execute('''
            INSERT INTO context_templates 
            (user_id, name, description, context_text, document_types, is_default)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, name, description, context_text, 
              json.dumps(document_types or []), 1 if is_default else 0))
        conn.commit()
        return cursor.lastrowid

def get_context_templates(
    user_id: int,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get user's context templates."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM context_templates WHERE user_id = ? ORDER BY is_default DESC, updated_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        templates = []
        for row in rows:
            t = dict(row)
            t['document_types'] = json.loads(t.get('document_types') or '[]')
            t['is_default'] = bool(t.get('is_default'))
            templates.append(t)
        return templates

def get_context_template(template_id: int, user_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific context template."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM context_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        ).fetchone()
        if row:
            t = dict(row)
            t['document_types'] = json.loads(t.get('document_types') or '[]')
            t['is_default'] = bool(t.get('is_default'))
            return t
        return None

def get_default_context_template(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user's default context template."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM context_templates WHERE user_id = ? AND is_default = 1",
            (user_id,)
        ).fetchone()
        if row:
            t = dict(row)
            t['document_types'] = json.loads(t.get('document_types') or '[]')
            t['is_default'] = True
            return t
        return None

def update_context_template(
    template_id: int,
    user_id: int,
    **updates
) -> bool:
    """Update a context template."""
    allowed = {'name', 'description', 'context_text', 'document_types', 'is_default'}
    valid_updates = {k: v for k, v in updates.items() if k in allowed and v is not None}

    if not valid_updates:
        return False

    with get_db_connection() as conn:

        if valid_updates.get('is_default'):
            conn.execute(
                "UPDATE context_templates SET is_default = 0 WHERE user_id = ?",
                (user_id,)
            )

        if 'document_types' in valid_updates:
            valid_updates['document_types'] = json.dumps(valid_updates['document_types'])
        if 'is_default' in valid_updates:
            valid_updates['is_default'] = 1 if valid_updates['is_default'] else 0

        valid_updates['updated_at'] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in valid_updates.keys())

        conn.execute(
            f"UPDATE context_templates SET {set_clause} WHERE id = ? AND user_id = ?",
            list(valid_updates.values()) + [template_id, user_id]
        )
        conn.commit()
        return True

def delete_context_template(template_id: int, user_id: int) -> bool:
    """Delete a context template."""
    with get_db_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM context_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def save_workspace_session(
    session_id: str,
    user_id: int,
    documents: Dict[str, Dict[str, Any]],
    active_document: Optional[str] = None,
    session_name: Optional[str] = None,
    playbook: Optional[str] = None,
    context_data: Optional[Dict[str, Any]] = None,
    docx_blobs: Optional[Dict[str, bytes]] = None
) -> bool:
    """
    Save or update a workspace session with encrypted documents.

    Args:
        session_id: Unique session identifier
        user_id: User ID
        documents: Dict of {path: {content, description, created_at, modified_at, format, is_synced}}
        active_document: Currently active document path
        session_name: Human-readable session name
        playbook: Playbook content for review context
        context_data: Additional session context (jurisdiction, representing, etc.)
        docx_blobs: Dict of {path: bytes} for native DOCX files

    Returns:
        True if saved successfully
    """
    from anylegal_oss.utils.encryption import encrypt_bytes, ENCRYPTION_AVAILABLE as BYTES_ENCRYPTION

    try:

        docs_json = json.dumps(documents)
        encrypted_docs = encrypt_text(docs_json)

        encrypted_playbook = encrypt_text(playbook) if playbook else None

        context_json = json.dumps(context_data) if context_data else None
        encrypted_context = encrypt_text(context_json) if context_json else None

        encrypted_docx_blobs = None
        if docx_blobs:

            import base64
            blobs_data = {}
            for path, blob in docx_blobs.items():
                encrypted_blob = encrypt_bytes(blob) if BYTES_ENCRYPTION else blob
                blobs_data[path] = base64.b64encode(encrypted_blob).decode('utf-8')
            encrypted_docx_blobs = json.dumps(blobs_data)

        with get_db_connection() as conn:

            existing = conn.execute(
                "SELECT id FROM document_sessions WHERE id = ?",
                (session_id,)
            ).fetchone()

            now = datetime.now().isoformat()

            if existing:

                conn.execute('''
                    UPDATE document_sessions SET
                        workspace_documents = ?,
                        current_content = ?,
                        playbook = ?,
                        context_data = ?,
                        session_name = ?,
                        is_encrypted = ?,
                        docx_blobs = ?,
                        updated_at = ?
                    WHERE id = ? AND user_id = ?
                ''', (
                    encrypted_docs,
                    active_document,
                    encrypted_playbook,
                    encrypted_context,
                    session_name,
                    1 if ENCRYPTION_AVAILABLE else 0,
                    encrypted_docx_blobs,
                    now,
                    session_id,
                    user_id
                ))
            else:

                conn.execute('''
                    INSERT INTO document_sessions 
                    (id, user_id, document_name, workspace_documents, current_content, 
                     playbook, context_data, session_name, is_encrypted, docx_blobs, created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    session_id,
                    user_id,
                    active_document or 'Untitled Session',
                    encrypted_docs,
                    active_document,
                    encrypted_playbook,
                    encrypted_context,
                    session_name or f"Session {now[:10]}",
                    1 if ENCRYPTION_AVAILABLE else 0,
                    encrypted_docx_blobs,
                    now,
                    now,
                    'active'
                ))

            conn.commit()
            docx_count = len(docx_blobs) if docx_blobs else 0
            logger.info(f"Workspace session {session_id} saved for user {user_id} (encrypted: {ENCRYPTION_AVAILABLE}, docx_files: {docx_count})")
            return True

    except Exception as e:
        logger.error(f"Failed to save workspace session: {e}")
        return False

def load_workspace_session(
    session_id: str,
    user_id: int
) -> Optional[Dict[str, Any]]:
    """
    Load a workspace session from the database.

    Args:
        session_id: Session identifier
        user_id: User ID (for access control)

    Returns:
        Dict with session data or None if not found
    """
    from anylegal_oss.utils.encryption import decrypt_bytes

    try:
        with get_db_connection() as conn:
            row = conn.execute('''
                SELECT id, user_id, document_name, workspace_documents, current_content,
                       playbook, context_data, session_name, is_encrypted, docx_blobs,
                       created_at, updated_at, status
                FROM document_sessions 
                WHERE id = ? AND user_id = ?
            ''', (session_id, user_id)).fetchone()

            if not row:
                return None

            result = dict(row)

            if result.get('workspace_documents'):
                decrypted_docs = decrypt_text(result['workspace_documents'])
                try:
                    result['documents'] = json.loads(decrypted_docs)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse documents JSON for session {session_id}")
                    result['documents'] = {}
            else:
                result['documents'] = {}

            if result.get('playbook'):
                result['playbook'] = decrypt_text(result['playbook'])

            if result.get('context_data'):
                decrypted_context = decrypt_text(result['context_data'])
                try:
                    result['context'] = json.loads(decrypted_context)
                except json.JSONDecodeError:
                    result['context'] = {}
            else:
                result['context'] = {}

            import base64
            raw_docx_blobs = result.get('docx_blobs')
            result['docx_blobs'] = {}
            if raw_docx_blobs:
                try:
                    blobs_data = json.loads(raw_docx_blobs)
                    for path, blob_b64 in blobs_data.items():
                        encrypted_blob = base64.b64decode(blob_b64)
                        result['docx_blobs'][path] = decrypt_bytes(encrypted_blob)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"Failed to decrypt DOCX blobs for session {session_id}: {e}")

            result['active_document'] = result.get('current_content')

            docx_count = len(result['docx_blobs'])
            logger.info(f"Loaded workspace session {session_id} with {len(result['documents'])} documents ({docx_count} DOCX files)")
            return result

    except Exception as e:
        logger.error(f"Failed to load workspace session: {e}")
        return None

def list_workspace_sessions(
    user_id: int,
    status: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    List workspace sessions for a user.

    Args:
        user_id: User ID
        status: Filter by status ('active', 'archived')
        limit: Maximum number of sessions to return

    Returns:
        List of session metadata (without full document content)
    """
    try:
        with get_db_connection() as conn:
            query = '''
                SELECT id, document_name, session_name, created_at, updated_at, status
                FROM document_sessions 
                WHERE user_id = ?
            '''
            params = [user_id]

            if status:
                query += " AND status = ?"
                params.append(status)

            query += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(query, params).fetchall()

            return [dict(row) for row in rows]

    except Exception as e:
        logger.error(f"Failed to list workspace sessions: {e}")
        return []

def delete_workspace_session(session_id: str, user_id: int) -> bool:
    """
    Delete a workspace session.

    Args:
        session_id: Session identifier
        user_id: User ID (for access control)

    Returns:
        True if deleted successfully
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM document_sessions WHERE id = ? AND user_id = ?",
                (session_id, user_id)
            )
            conn.commit()
            deleted = cursor.rowcount > 0

            if deleted:
                logger.info(f"Deleted workspace session {session_id}")

            return deleted

    except Exception as e:
        logger.error(f"Failed to delete workspace session: {e}")
        return False

def get_session_document(
    session_id: str,
    user_id: int,
    document_path: str
) -> Optional[Dict[str, Any]]:
    """
    Get a specific document from a workspace session.

    Args:
        session_id: Session identifier
        user_id: User ID (for access control)
        document_path: Path of the document within the session

    Returns:
        Document data with content, or None if not found
    """
    session = load_workspace_session(session_id, user_id)
    if not session:
        return None

    documents = session.get('documents', {})
    return documents.get(document_path)

def migrate_create_workspaces_table():
    """
    Create the workspaces table for persistent user workspaces.
    Also adds workspace_id column to threads and agentic_messages.

    Idempotent — safe to call on every startup.
    """
    with get_db_connection() as conn:

        conn.execute('''
            CREATE TABLE IF NOT EXISTS workspaces (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL UNIQUE,
                workspace_documents TEXT,
                playbook TEXT,
                context_data TEXT,
                docx_blobs BLOB,
                is_encrypted INTEGER DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        ''')
        conn.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS idx_workspaces_user ON workspaces(user_id)'
        )

        cursor = conn.execute("PRAGMA table_info(threads)")
        thread_cols = {row['name'] for row in cursor.fetchall()}
        if 'workspace_id' not in thread_cols:
            try:
                conn.execute("ALTER TABLE threads ADD COLUMN workspace_id TEXT")
                logger.info("Migration: added workspace_id to threads table")
            except Exception as e:
                logger.debug(f"threads.workspace_id migration skipped: {e}")

        cursor = conn.execute("PRAGMA table_info(agentic_messages)")
        am_cols = {row['name'] for row in cursor.fetchall()}
        if 'workspace_id' not in am_cols:
            try:
                conn.execute("ALTER TABLE agentic_messages ADD COLUMN workspace_id TEXT")
                conn.execute(
                    'CREATE INDEX IF NOT EXISTS idx_agentic_messages_workspace '
                    'ON agentic_messages(workspace_id)'
                )
                logger.info("Migration: added workspace_id to agentic_messages table")
            except Exception as e:
                logger.debug(f"agentic_messages.workspace_id migration skipped: {e}")

        conn.commit()
        logger.info("Workspaces table migration complete")

def save_workspace(
    workspace_id: str,
    user_id: int,
    documents: Dict[str, Dict[str, Any]],
    active_document: Optional[str] = None,
    playbook: Optional[str] = None,
    context_data: Optional[Dict[str, Any]] = None,
    docx_blobs: Optional[Dict[str, bytes]] = None
) -> bool:
    """
    Save or update a persistent workspace.

    Uses the same encryption strategy as save_workspace_session.
    """
    from anylegal_oss.utils.encryption import encrypt_bytes, ENCRYPTION_AVAILABLE as BYTES_ENCRYPTION

    try:

        docs_json = json.dumps(documents)
        encrypted_docs = encrypt_text(docs_json)

        encrypted_playbook = encrypt_text(playbook) if playbook else None

        context_json = json.dumps(context_data) if context_data else None
        encrypted_context = encrypt_text(context_json) if context_json else None

        encrypted_docx_blobs = None
        if docx_blobs:
            import base64
            blobs_data = {}
            for path, blob in docx_blobs.items():
                encrypted_blob = encrypt_bytes(blob) if BYTES_ENCRYPTION else blob
                blobs_data[path] = base64.b64encode(encrypted_blob).decode('utf-8')
            encrypted_docx_blobs = json.dumps(blobs_data)

        with get_db_connection() as conn:
            existing = conn.execute(
                "SELECT id FROM workspaces WHERE id = ?", (workspace_id,)
            ).fetchone()

            now = datetime.now().isoformat()

            if existing:
                conn.execute('''
                    UPDATE workspaces SET
                        workspace_documents = ?,
                        playbook = ?,
                        context_data = ?,
                        is_encrypted = ?,
                        docx_blobs = ?,
                        updated_at = ?
                    WHERE id = ? AND user_id = ?
                ''', (
                    encrypted_docs,
                    encrypted_playbook,
                    encrypted_context,
                    1 if ENCRYPTION_AVAILABLE else 0,
                    encrypted_docx_blobs,
                    now,
                    workspace_id,
                    user_id,
                ))
            else:
                conn.execute('''
                    INSERT INTO workspaces
                    (id, user_id, workspace_documents, playbook, context_data,
                     is_encrypted, docx_blobs, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    workspace_id,
                    user_id,
                    encrypted_docs,
                    encrypted_playbook,
                    encrypted_context,
                    1 if ENCRYPTION_AVAILABLE else 0,
                    encrypted_docx_blobs,
                    now,
                    now,
                ))

            conn.commit()
            docx_count = len(docx_blobs) if docx_blobs else 0
            logger.info(
                f"Workspace {workspace_id} saved for user {user_id} "
                f"(encrypted: {ENCRYPTION_AVAILABLE}, docx_files: {docx_count})"
            )
            return True

    except Exception as e:
        logger.error(f"Failed to save workspace: {e}")
        return False

def load_workspace_by_user(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Load the persistent workspace for a user.

    Returns:
        Dict with workspace data or None if no workspace exists.
    """
    from anylegal_oss.utils.encryption import decrypt_bytes

    try:
        with get_db_connection() as conn:
            row = conn.execute('''
                SELECT id, user_id, workspace_documents, playbook, context_data,
                       is_encrypted, docx_blobs, created_at, updated_at
                FROM workspaces
                WHERE user_id = ?
            ''', (user_id,)).fetchone()

            if not row:
                return None

            result = dict(row)

            if result.get('workspace_documents'):
                decrypted_docs = decrypt_text(result['workspace_documents'])
                try:
                    result['documents'] = json.loads(decrypted_docs)
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse documents JSON for workspace {result['id']}")
                    result['documents'] = {}
            else:
                result['documents'] = {}

            if result.get('playbook'):
                result['playbook'] = decrypt_text(result['playbook'])

            if result.get('context_data'):
                decrypted_context = decrypt_text(result['context_data'])
                try:
                    result['context'] = json.loads(decrypted_context)
                except json.JSONDecodeError:
                    result['context'] = {}
            else:
                result['context'] = {}

            import base64
            raw_docx_blobs = result.get('docx_blobs')
            result['docx_blobs'] = {}
            if raw_docx_blobs:
                try:
                    blobs_data = json.loads(raw_docx_blobs)
                    for path, blob_b64 in blobs_data.items():
                        encrypted_blob = base64.b64decode(blob_b64)
                        result['docx_blobs'][path] = decrypt_bytes(encrypted_blob)
                except (json.JSONDecodeError, Exception) as e:
                    logger.error(f"Failed to decrypt DOCX blobs for workspace {result['id']}: {e}")

            docx_count = len(result['docx_blobs'])
            logger.info(
                f"Loaded workspace {result['id']} for user {user_id} "
                f"with {len(result['documents'])} documents ({docx_count} DOCX files)"
            )
            return result

    except Exception as e:
        logger.error(f"Failed to load workspace for user {user_id}: {e}")
        return None

def delete_workspace(workspace_id: str, user_id: int) -> bool:
    """Delete a persistent workspace."""
    try:
        with get_db_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM workspaces WHERE id = ? AND user_id = ?",
                (workspace_id, user_id)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted workspace {workspace_id} for user {user_id}")
            return deleted
    except Exception as e:
        logger.error(f"Failed to delete workspace: {e}")
        return False

def migrate_sessions_to_workspaces():
    """
    One-time migration: for each user with document_sessions but no workspace
    (or an empty workspace), copy the most recent active session into the
    workspaces table.

    Idempotent — skips users who already have a non-empty workspace.
    """
    import uuid as _uuid

    try:
        with get_db_connection() as conn:

            rows = conn.execute('''
                SELECT DISTINCT ds.user_id
                FROM document_sessions ds
                LEFT JOIN workspaces w ON w.user_id = ds.user_id
                WHERE w.id IS NULL
                   OR (w.workspace_documents IS NULL OR w.workspace_documents = '')
                ORDER BY ds.user_id
            ''').fetchall()

            migrated = 0
            for row in rows:
                uid = row['user_id']

                session_row = conn.execute('''
                    SELECT id, workspace_documents, playbook, context_data,
                           docx_blobs, is_encrypted
                    FROM document_sessions
                    WHERE user_id = ? AND status = 'active'
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''', (uid,)).fetchone()

                if not session_row:
                    continue

                now = datetime.now().isoformat()

                existing = conn.execute(
                    'SELECT id FROM workspaces WHERE user_id = ?', (uid,)
                ).fetchone()

                if existing:

                    conn.execute('''
                        UPDATE workspaces SET
                            workspace_documents = ?,
                            playbook = ?,
                            context_data = ?,
                            is_encrypted = ?,
                            docx_blobs = ?,
                            updated_at = ?
                        WHERE user_id = ?
                    ''', (
                        session_row['workspace_documents'],
                        session_row['playbook'],
                        session_row['context_data'],
                        session_row['is_encrypted'],
                        session_row['docx_blobs'],
                        now,
                        uid,
                    ))
                else:
                    workspace_id = str(_uuid.uuid4())
                    conn.execute('''
                        INSERT INTO workspaces
                        (id, user_id, workspace_documents, playbook, context_data,
                         is_encrypted, docx_blobs, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        workspace_id,
                        uid,
                        session_row['workspace_documents'],
                        session_row['playbook'],
                        session_row['context_data'],
                        session_row['is_encrypted'],
                        session_row['docx_blobs'],
                        now,
                        now,
                    ))
                migrated += 1

            conn.commit()
            if migrated:
                logger.info(f"Migrated {migrated} users' sessions into workspaces table")
            else:
                logger.info("No sessions to migrate (all users already have workspaces)")

    except Exception as e:
        logger.error(f"Failed to migrate sessions to workspaces: {e}")

