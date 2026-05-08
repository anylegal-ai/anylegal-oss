"""
Thin async wrappers around sync DB functions. Each wrapper runs the underlying
sync call in the default asyncio executor (``asyncio.to_thread``), so the event
loop is never blocked by SQLite I/O.

This is deliberate: SQLite is not async-native, and the existing sync functions
are battle-tested across Flask callers. We do not rewrite them — we adapt the
boundary instead.

Flask callers keep using the sync functions directly from
``anylegal_oss.db.database`` / ``anylegal_oss.workspace.db``. FastAPI and the
async agent import from this module.
"""

import asyncio
from typing import Any, Dict, List, Optional

from anylegal_oss.db import database as _database
from anylegal_oss.workspace import db as _workspace_db

async def save_agentic_message(
    *,
    session_id: str,
    thread_id: Optional[str],
    user_id: int,
    message_type: str,
    content: Optional[str] = None,
    tool_name: Optional[str] = None,
    tool_call_id: Optional[str] = None,
    tool_arguments: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_used: Optional[int] = None,
    cost: Optional[float] = None,
) -> Optional[int]:
    """Async wrapper for ``database.save_agentic_message``."""
    return await asyncio.to_thread(
        _database.save_agentic_message,
        session_id=session_id,
        thread_id=thread_id,
        user_id=user_id,
        message_type=message_type,
        content=content,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        tool_arguments=tool_arguments,
        model_used=model_used,
        tokens_used=tokens_used,
        cost=cost,
    )

async def get_agentic_thread_messages(
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Async wrapper for ``database.get_agentic_thread_messages``."""
    return await asyncio.to_thread(
        _database.get_agentic_thread_messages,
        thread_id=thread_id,
        session_id=session_id,
        limit=limit,
    )

async def load_workspace_session(
    session_id: str,
    user_id: int,
) -> Optional[Dict[str, Any]]:
    """Async wrapper for ``workspace.db.load_workspace_session``."""
    return await asyncio.to_thread(
        _workspace_db.load_workspace_session,
        session_id,
        user_id,
    )

async def save_workspace_session(*args: Any, **kwargs: Any) -> Any:
    """Async wrapper for ``workspace.db.save_workspace_session``."""
    return await asyncio.to_thread(
        _workspace_db.save_workspace_session,
        *args,
        **kwargs,
    )
