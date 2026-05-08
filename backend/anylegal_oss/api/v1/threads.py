"""Thread CRUD routes — FastAPI."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from anylegal_oss.db.database import (
    get_db_connection,
    create_thread,
    get_user_threads,
    get_thread_messages,
    log_chat_to_thread,
)

logger = logging.getLogger(__name__)

OSS_USER_ID = 1

router = APIRouter(prefix="/api/v1", tags=["threads"])

def get_formatted_thread_history(thread_id: str, limit: int = 10) -> list[dict]:
    """Fetch and format thread history for the agent."""
    if not thread_id:
        return []
    try:
        raw_messages = get_thread_messages(thread_id, limit=limit * 2, offset=0)
        formatted = []
        for msg in reversed(raw_messages):
            role = msg['role']
            content = msg['content']
            if role in ('user', 'assistant') and content:
                formatted.append({"role": role, "content": content})
            if len(formatted) >= limit * 2:
                break
        return formatted[-(limit * 2):]
    except Exception as e:
        logger.error(f"Error fetching thread {thread_id} history: {e}", exc_info=True)
        return []

@router.get("/threads")
def list_threads(page: int = 1, limit: int = 20):
    """List threads for the OSS user."""
    try:
        if page < 1:
            page = 1
        if limit < 1:
            limit = 20
        if limit > 100:
            limit = 100
        offset = (page - 1) * limit

        threads_data = get_user_threads(OSS_USER_ID, limit, offset)
        with get_db_connection() as conn:
            total_count = conn.execute(
                'SELECT COUNT(*) as count FROM threads WHERE user_id = ?',
                (OSS_USER_ID,),
            ).fetchone()['count']

        thread_list = []
        for row in threads_data:
            thread_list.append({
                "id": str(row['id']),
                "title": row['title'],
                "created_at": row['created_at'],
                "updated_at": row['updated_at'],
                "jurisdiction": row['jurisdiction'],
                "source": row['source'] if 'source' in row.keys() else 'web',
            })

        return {
            "threads": thread_list,
            "total_count": total_count,
            "page": page,
            "limit": limit,
        }
    except Exception as e:
        logger.error(f"Error listing threads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve threads")

@router.post("/threads", status_code=201)
async def create_new_thread(request: Request):
    """Create a new thread."""
    try:
        try:
            data = await request.json() if await _has_body(request) else {}
        except Exception:
            data = {}
        title = (data or {}).get('title', 'New Thread')
        jurisdiction = (data or {}).get('jurisdiction')

        thread_id = create_thread(OSS_USER_ID, title, jurisdiction)
        with get_db_connection() as conn:
            new_row = conn.execute(
                "SELECT id, title, created_at, updated_at, jurisdiction FROM threads WHERE id = ?",
                (thread_id,),
            ).fetchone()

        if not new_row:
            raise HTTPException(status_code=500, detail="Failed to create thread")

        return {
            "id": str(new_row['id']),
            "title": new_row['title'],
            "created_at": new_row['created_at'],
            "updated_at": new_row['updated_at'],
            "jurisdiction": new_row['jurisdiction'],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating thread: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create thread")

async def _has_body(request: Request) -> bool:
    """Quick check whether the incoming request has a JSON body."""
    cl = request.headers.get('content-length')
    return bool(cl and int(cl) > 0)

@router.get("/threads/{thread_id}")
def get_thread(thread_id: str, limit: int = 50, offset: int = 0):
    """Get a thread with its messages."""
    with get_db_connection() as conn:
        thread = conn.execute(
            'SELECT id, title, created_at, updated_at, jurisdiction FROM threads WHERE id = ? AND user_id = ?',
            (thread_id, OSS_USER_ID),
        ).fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

    messages = get_thread_messages(thread_id, limit, offset)
    message_list = [
        {
            "id": m['id'],
            "role": m['role'],
            "content": m['content'],
            "timestamp": m['timestamp'],
        }
        for m in messages
    ]
    return {
        "id": str(thread['id']),
        "title": thread['title'],
        "created_at": thread['created_at'],
        "updated_at": thread['updated_at'],
        "jurisdiction": thread['jurisdiction'],
        "messages": message_list,
    }

@router.put("/threads/{thread_id}")
async def update_thread(thread_id: str, request: Request):
    """Update a thread's title and/or jurisdiction."""
    with get_db_connection() as conn:
        thread = conn.execute(
            'SELECT * FROM threads WHERE id = ? AND user_id = ?',
            (thread_id, OSS_USER_ID),
        ).fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

    data = await request.json()
    title = data.get('title')
    jurisdiction = data.get('jurisdiction')
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    with get_db_connection() as conn:
        if jurisdiction:
            conn.execute(
                'UPDATE threads SET title = ?, jurisdiction = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (title, jurisdiction, thread_id),
            )
        else:
            conn.execute(
                'UPDATE threads SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (title, thread_id),
            )
        conn.commit()
        updated = conn.execute(
            "SELECT id, title, updated_at, jurisdiction FROM threads WHERE id = ?",
            (thread_id,),
        ).fetchone()

    return {
        "id": str(updated['id']),
        "title": updated['title'],
        "updated_at": updated['updated_at'],
        "jurisdiction": updated['jurisdiction'],
    }

@router.delete("/threads/{thread_id}")
def delete_thread(thread_id: str):
    """Delete a thread."""
    with get_db_connection() as conn:
        thread = conn.execute(
            'SELECT * FROM threads WHERE id = ? AND user_id = ?',
            (thread_id, OSS_USER_ID),
        ).fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        conn.execute('DELETE FROM threads WHERE id = ?', (thread_id,))
        conn.commit()
    return {"success": True}

@router.post("/threads/{thread_id}/messages")
async def add_thread_messages(thread_id: str, request: Request):
    """Persist a user/assistant message pair to a thread."""
    with get_db_connection() as conn:
        thread = conn.execute(
            'SELECT id FROM threads WHERE id = ? AND user_id = ?',
            (thread_id, OSS_USER_ID),
        ).fetchone()
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

    try:
        data = await request.json()
        user_message = data.get('user_message')
        assistant_message = data.get('assistant_message')
        if not user_message or not assistant_message:
            raise HTTPException(
                status_code=400,
                detail="Both user_message and assistant_message are required",
            )

        log_chat_to_thread(
            user_id=OSS_USER_ID,
            message=user_message,
            response=assistant_message,
            thread_id=thread_id,
            encrypt=True,
        )
        return {"success": True, "thread_id": thread_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error persisting messages to thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to persist messages")
