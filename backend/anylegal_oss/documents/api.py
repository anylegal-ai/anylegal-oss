"""Document storage API — FastAPI.

Endpoints for storing, retrieving, and managing user documents
with encryption at rest.
"""

import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from anylegal_oss.db.database import get_db_connection
from anylegal_oss.utils.encryption import encrypt_text, decrypt_text, ENCRYPTION_AVAILABLE

logger = logging.getLogger(__name__)

OSS_USER_ID = 1

router = APIRouter(tags=["documents"])

def strip_html_tags(html_content: str) -> str:
    """Strip HTML tags from content to get plain text."""
    if not html_content:
        return ''
    text = re.sub(r'<[^>]+>', ' ', html_content)
    text = (
        text.replace('&nbsp;', ' ')
            .replace('&amp;', '&')
            .replace('&lt;', '<')
            .replace('&gt;', '>')
            .replace('&quot;', '"')
    )
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def ensure_documents_table():
    """Create the documents table if it doesn't exist."""
    with get_db_connection() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_documents (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                content_preview TEXT,
                document_type TEXT DEFAULT 'general',
                word_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_encrypted INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_documents_user
            ON user_documents(user_id)
        ''')
        conn.commit()

ensure_documents_table()

@router.get('/documents')
def list_documents():
    """List all documents for the OSS user."""
    try:
        with get_db_connection() as conn:
            docs = conn.execute('''
                SELECT id, title, content_preview, document_type, word_count,
                       created_at, updated_at
                FROM user_documents
                WHERE user_id = ?
                ORDER BY updated_at DESC
            ''', (OSS_USER_ID,)).fetchall()

            documents = [{
                'id': doc['id'],
                'title': doc['title'],
                'preview': decrypt_text(doc['content_preview']) if doc['content_preview'] else '',
                'document_type': doc['document_type'],
                'word_count': doc['word_count'],
                'created_at': doc['created_at'],
                'updated_at': doc['updated_at'],
            } for doc in docs]

            return {"documents": documents}
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        raise HTTPException(status_code=500, detail="Failed to list documents")

@router.post('/documents', status_code=201)
async def create_document(request: Request):
    """Create a new document."""
    data = await request.json()
    if not data or not data.get('content'):
        raise HTTPException(status_code=400, detail="Missing required field: content")

    try:
        doc_id = str(uuid.uuid4())
        title = data.get('title', 'Untitled Document')
        content = data['content']
        document_type = data.get('document_type', 'general')

        plain_text = strip_html_tags(content)
        word_count = len(plain_text.split())
        preview_text = plain_text[:200] + ('...' if len(plain_text) > 200 else '')
        preview = encrypt_text(preview_text) if ENCRYPTION_AVAILABLE else preview_text
        encrypted_content = encrypt_text(content) if ENCRYPTION_AVAILABLE else content
        is_encrypted = 1 if ENCRYPTION_AVAILABLE else 0

        with get_db_connection() as conn:
            conn.execute('''
                INSERT INTO user_documents
                (id, user_id, title, content, content_preview, document_type, word_count, is_encrypted)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (doc_id, OSS_USER_ID, title, encrypted_content, preview, document_type, word_count, is_encrypted))
            conn.commit()

        return {
            "id": doc_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating document: {e}")
        raise HTTPException(status_code=500, detail="Failed to create document")

@router.get('/documents/{doc_id}')
def get_document(doc_id: str):
    """Get a specific document by ID."""
    try:
        with get_db_connection() as conn:
            doc = conn.execute('''
                SELECT id, title, content, document_type, word_count,
                       created_at, updated_at, is_encrypted
                FROM user_documents
                WHERE id = ? AND user_id = ?
            ''', (doc_id, OSS_USER_ID)).fetchone()

            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            content = doc['content']
            if doc['is_encrypted']:
                content = decrypt_text(content)

            return {
                'id': doc['id'],
                'title': doc['title'],
                'content': content,
                'document_type': doc['document_type'],
                'word_count': doc['word_count'],
                'created_at': doc['created_at'],
                'updated_at': doc['updated_at'],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get document")

@router.put('/documents/{doc_id}')
async def update_document(doc_id: str, request: Request):
    """Update a document."""
    data = await request.json()
    if not data:
        raise HTTPException(status_code=400, detail="No data provided")

    try:
        with get_db_connection() as conn:
            doc = conn.execute(
                'SELECT id FROM user_documents WHERE id = ? AND user_id = ?',
                (doc_id, OSS_USER_ID),
            ).fetchone()
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            updates = []
            params = []

            if 'title' in data:
                updates.append('title = ?')
                params.append(data['title'])

            if 'content' in data:
                content = data['content']
                plain_text = strip_html_tags(content)
                word_count = len(plain_text.split())
                preview_text = plain_text[:200] + ('...' if len(plain_text) > 200 else '')
                preview = encrypt_text(preview_text) if ENCRYPTION_AVAILABLE else preview_text
                encrypted_content = encrypt_text(content) if ENCRYPTION_AVAILABLE else content

                updates.append('content = ?')
                params.append(encrypted_content)
                updates.append('content_preview = ?')
                params.append(preview)
                updates.append('word_count = ?')
                params.append(word_count)
                updates.append('is_encrypted = ?')
                params.append(1 if ENCRYPTION_AVAILABLE else 0)

            if 'document_type' in data:
                updates.append('document_type = ?')
                params.append(data['document_type'])

            if updates:
                updates.append('updated_at = CURRENT_TIMESTAMP')
                params.extend([doc_id, OSS_USER_ID])
                conn.execute(
                    f"UPDATE user_documents SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
                    params,
                )
                conn.commit()

            return {"success": True, "id": doc_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update document")

@router.delete('/documents/{doc_id}')
def delete_document(doc_id: str):
    """Delete a document."""
    try:
        with get_db_connection() as conn:
            result = conn.execute(
                'DELETE FROM user_documents WHERE id = ? AND user_id = ?',
                (doc_id, OSS_USER_ID),
            )
            conn.commit()
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Document not found")
            return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {doc_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete document")
