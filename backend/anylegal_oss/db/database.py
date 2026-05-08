import sqlite3
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, List
import uuid
import logging
import random
import time

try:
    from anylegal_oss.utils.encryption import encrypt_text, decrypt_text, ENCRYPTION_AVAILABLE
except ImportError:
    ENCRYPTION_AVAILABLE = False
    def encrypt_text(text): return text
    def decrypt_text(text): return text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'anylegal_oss.db'))

db_dir = os.path.dirname(DATABASE_PATH)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)

def init_db():
    """OSS is single-tenant: one row in `users` (id=1)."""
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            preferred_model TEXT,
            global_instructions TEXT
        );

        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT NOT NULL,
            response TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            tool_args_tokens INTEGER DEFAULT 0,
            tool_response_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            jurisdiction TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        ''')
        conn.execute("INSERT OR IGNORE INTO users (id) VALUES (1)")
        conn.commit()

def get_db_connection():
    # WAL + a 10s busy_timeout makes "database is locked" rare under the
    # asyncio.to_thread / multi-worker concurrency we run today. If write
    # contention shows up under real load, swap to aiosqlite at the boundary.
    conn = sqlite3.connect(DATABASE_PATH, timeout=10, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn

def ensure_schema():
    with get_db_connection() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        if 'threads' not in tables:
            conn.execute('''
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL DEFAULT 'New Thread',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    jurisdiction TEXT,
                    source TEXT DEFAULT 'web',
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')
            conn.execute('CREATE INDEX idx_threads_user_id ON threads (user_id)')
            conn.execute('CREATE INDEX idx_threads_updated_at ON threads (updated_at DESC)')
            logger.info("Schema Check: Created threads table")

        if 'thread_messages' not in tables:
            conn.execute('''
                CREATE TABLE thread_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (thread_id) REFERENCES threads (id) ON DELETE CASCADE
                )
            ''')
            conn.execute('CREATE INDEX idx_thread_messages_thread_id ON thread_messages (thread_id)')
            logger.info("Schema Check: Created thread_messages table")

        if 'agentic_messages' not in tables:
            conn.execute('''
                CREATE TABLE agentic_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    thread_id TEXT,
                    user_id INTEGER NOT NULL,
                    message_type TEXT NOT NULL,
                    content TEXT,
                    tool_name TEXT,
                    tool_call_id TEXT,
                    tool_arguments TEXT,
                    model_used TEXT,
                    tokens_used INTEGER,
                    cost REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agentic_messages_session ON agentic_messages(session_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agentic_messages_thread ON agentic_messages(thread_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_agentic_messages_user ON agentic_messages(user_id)')
            logger.info("Schema Check: Created agentic_messages table")

        conn.commit()

def create_thread(user_id, title=None, jurisdiction=None, thread_type=None, document_id=None, document_name=None, source='web'):
    with get_db_connection() as conn:
        title = title or 'New Thread'
        thread_id = str(uuid.uuid4())
        final_jurisdiction = jurisdiction or 'GENERAL'
        try:
            conn.execute('''
                INSERT INTO threads (id, user_id, title, jurisdiction, source)
                VALUES (?, ?, ?, ?, ?)
            ''', (thread_id, int(user_id), str(title), final_jurisdiction, source))
            conn.commit()
            verification = conn.execute('SELECT id FROM threads WHERE id = ?', (thread_id,)).fetchone()
            if verification: return thread_id
            else: return None
        except Exception as e:
            logger.error(f"Error creating thread: {e}")
            conn.rollback()
            return None

def get_user_threads(user_id, limit=20, offset=0, thread_type=None):
    with get_db_connection() as conn:
        try:
            threads = conn.execute('''
                SELECT id, title, created_at, updated_at, jurisdiction, source
                FROM threads
                WHERE user_id = ? AND id IS NOT NULL AND id != 'None'
                ORDER BY datetime(updated_at) DESC LIMIT ? OFFSET ? ''',
                (user_id, limit, offset)).fetchall()
            return threads
        except Exception as e:
            logger.error(f"Error getting threads for user {user_id}: {e}")
            return []

def get_threads_by_document_id(user_id, document_id, limit=10):
    return []

def update_thread_document_id(thread_id, document_id, document_name=None):
    return True

def get_thread_messages(thread_id: str, limit=50, offset=0):
    """Get messages from a thread, decrypting content if needed."""
    thread_id_str = str(thread_id)
    with get_db_connection() as conn:
        messages = conn.execute('''
            SELECT rowid as id, role, content, timestamp FROM thread_messages
            WHERE thread_id = ? ORDER BY timestamp ASC LIMIT ? OFFSET ? ''',
            (thread_id_str, limit, offset)).fetchall()

        decrypted_messages = []
        for msg in messages:
            decrypted_messages.append({
                'id': msg['id'],
                'role': msg['role'],
                'content': decrypt_text(msg['content']),
                'timestamp': msg['timestamp']
            })

        return decrypted_messages

def update_thread_title(thread_id: str, title: str):
    thread_id_str = str(thread_id)
    with get_db_connection() as conn:
        conn.execute('UPDATE threads SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (title, thread_id_str))
        conn.commit()
        return True

def update_thread_timestamp(thread_id: str):
    thread_id_str = str(thread_id)
    with get_db_connection() as conn:
        conn.execute('UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (thread_id_str,))
        conn.commit()
        return True

def log_chat_to_thread(user_id, message, response, thread_id=None, tokens: Optional[Dict[str, int]] = None, jurisdiction: Optional[str] = None, encrypt: bool = True):
    with get_db_connection() as conn:
        final_jurisdiction = jurisdiction or 'GENERAL'

        stored_message = encrypt_text(message) if encrypt and ENCRYPTION_AVAILABLE else message
        stored_response = encrypt_text(response) if encrypt and ENCRYPTION_AVAILABLE else response

        if thread_id is None:
            thread_id = str(uuid.uuid4())
            title = message[:50] + ('...' if len(message) > 50 else '')
            conn.execute('INSERT INTO threads (id, user_id, title, jurisdiction) VALUES (?, ?, ?, ?)',
                (thread_id, user_id, title, final_jurisdiction))

        conn.execute('INSERT INTO thread_messages (thread_id, role, content) VALUES (?, ?, ?)', (thread_id, 'user', stored_message))
        conn.execute('INSERT INTO thread_messages (thread_id, role, content) VALUES (?, ?, ?)', (thread_id, 'assistant', stored_response))
        conn.execute('UPDATE threads SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (thread_id,))

        prompt_t = tokens.get('prompt', 0) if tokens else 0
        completion_t = tokens.get('completion', 0) if tokens else 0
        tool_args_t = tokens.get('tool_args', 0) if tokens else 0
        tool_response_t = tokens.get('tool_responses', 0) if tokens else 0
        total_t = tokens.get('total', (prompt_t + completion_t + tool_args_t + tool_response_t)) if tokens else (prompt_t + completion_t + tool_args_t + tool_response_t)

        conn.execute(
            '''INSERT INTO chat_history (user_id, message, response,
                                      prompt_tokens, completion_tokens,
                                      tool_args_tokens, tool_response_tokens, total_tokens, jurisdiction)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_id, stored_message, stored_response,
             prompt_t, completion_t, tool_args_t, tool_response_t, total_t, final_jurisdiction)
        )
        return thread_id

def save_agentic_message(
    session_id: Optional[str], thread_id: Optional[str], user_id: int,
    message_type: str, content: Optional[str] = None,
    tool_name: Optional[str] = None, tool_call_id: Optional[str] = None,
    tool_arguments: Optional[str] = None, model_used: Optional[str] = None,
    tokens_used: Optional[int] = None, cost: Optional[float] = None
) -> int:
    with get_db_connection() as conn:
        cursor = conn.execute('''
            INSERT INTO agentic_messages
                (session_id, thread_id, user_id, message_type, content,
                 tool_name, tool_call_id, tool_arguments, model_used, tokens_used, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (session_id, thread_id, user_id, message_type, content,
              tool_name, tool_call_id, tool_arguments, model_used, tokens_used, cost))
        conn.commit()
        return cursor.lastrowid

def get_agentic_thread_messages(thread_id: Optional[str] = None, session_id: Optional[str] = None, limit: int = 200) -> List[Dict[str, Any]]:
    with get_db_connection() as conn:
        if thread_id:
            rows = conn.execute(
                'SELECT * FROM agentic_messages WHERE thread_id = ? ORDER BY created_at ASC LIMIT ?',
                (thread_id, limit)
            ).fetchall()
        elif session_id:
            rows = conn.execute(
                'SELECT * FROM agentic_messages WHERE session_id = ? ORDER BY created_at ASC LIMIT ?',
                (session_id, limit)
            ).fetchall()
        else:
            return []
        return [dict(row) for row in rows]

def get_user_balance(user_id: int) -> Dict[str, Any]:

    return {"subscription_tier": "oss", "balance": 0.0}

def get_user_preferred_model(user_id: int) -> Optional[str]:
    with get_db_connection() as conn:
        result = conn.execute(
            'SELECT preferred_model FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        return result['preferred_model'] if result else None

def set_user_preferred_model(user_id: int, model_id: str) -> bool:
    with get_db_connection() as conn:
        try:
            conn.execute(
                'UPDATE users SET preferred_model = ? WHERE id = ?',
                (model_id, user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error setting preferred model for user {user_id}: {e}")
            return False

def get_user_global_instructions(user_id: int) -> Optional[str]:
    if not user_id:
        return None
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT global_instructions FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
    except Exception as e:
        logger.warning(f"get_user_global_instructions failed for user {user_id}: {e}")
        return None
    if not row:
        return None
    val = row['global_instructions']
    if not isinstance(val, str):
        return None
    val = val.strip()
    return val or None

def set_user_global_instructions(user_id: int, content: Optional[str]) -> bool:
    if not user_id:
        return False
    try:
        with get_db_connection() as conn:
            conn.execute(
                "UPDATE users SET global_instructions = ? WHERE id = ?",
                (content, user_id),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.warning(f"set_user_global_instructions failed for user {user_id}: {e}")
        return False