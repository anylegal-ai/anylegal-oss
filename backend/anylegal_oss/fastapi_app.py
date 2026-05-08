import os
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, AsyncGenerator, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import StreamingResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid

from anylegal_oss.workspace.session import WorkspaceSession
from anylegal_oss.workspace.workspace import Workspace
from anylegal_oss.workspace.agentic_chat_async import create_agentic_chat_async
from anylegal_oss.state.session_guard import AsyncSessionGuard
from anylegal_oss.state.transcript import record_transcript, flush_session_storage

OSS_USER_ID = 1

from anylegal_oss.db.database import get_user_preferred_model

from anylegal_oss.services import (
    get_metrics,
    validate_agentic_request,
)

from anylegal_oss.api.v1 import models as _models_module
from anylegal_oss.api.v1 import threads as _threads_module
from anylegal_oss.documents.api import router as _documents_router
from anylegal_oss.workspace import workspace_router as _workspace_router

_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if not logging.getLogger().handlers:
    logging.basicConfig(
        level=_LOG_LEVEL,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
logging.getLogger("anylegal_oss").setLevel(_LOG_LEVEL)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI agentic service starting")

    # DB and workspace migrations are not optional: a half-migrated schema
    # serves 500s at runtime. Fail-fast so the process exits with logs the
    # operator can act on rather than silently boot into a broken state.
    from anylegal_oss.db.database import init_db, ensure_schema
    from anylegal_oss.workspace.db import (
        init_document_editor_tables,
        migrate_document_sessions_table,
        migrate_create_workspaces_table,
        migrate_sessions_to_workspaces,
    )
    from anylegal_oss.lexwiki_compiler.db import migrate_create_workspace_wikis_table

    init_db()
    ensure_schema()
    init_document_editor_tables()
    migrate_document_sessions_table()
    migrate_create_workspaces_table()
    migrate_sessions_to_workspaces()
    migrate_create_workspace_wikis_table()

    # Workspace seeding is best-effort: an empty workspace is a usable
    # state, so a seeding error should not block the service.
    try:
        from anylegal_oss.workspace.bootstrap import seed_default_workspace_if_empty
        seed_default_workspace_if_empty(user_id=OSS_USER_ID)
    except Exception as e:
        logger.warning(f"Workspace seeding skipped: {e}", exc_info=True)

    app.state.session_guard = AsyncSessionGuard()

    yield

    logger.info("FastAPI agentic service shutting down")

app = FastAPI(
    title="AnyLegal Agentic API",
    description="Async agentic chat endpoints",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Accept-Language"],
)

app.include_router(_models_module.router)
app.include_router(_threads_module.router)
app.include_router(_documents_router, prefix="/api/v1")
app.include_router(_workspace_router)

def _env_flag(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")

def _check_chat_killswitch():

    if not _env_flag("CHAT_ENABLED", "true"):
        raise HTTPException(status_code=503, detail="chat temporarily disabled")

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "fastapi-agentic",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "chat_enabled": _env_flag("CHAT_ENABLED", "true"),
    }

@app.get("/metrics")
async def metrics_endpoint():
    metrics = get_metrics()
    output = metrics.export_prometheus()
    return PlainTextResponse(content=output, media_type="text/plain")

@app.post("/api/v1/agentic/chat")
async def agentic_chat(
    request: Request,
    validation: dict = Depends(validate_agentic_request)
):
    _check_chat_killswitch()
    user_id = OSS_USER_ID
    session_id = validation.session_id
    message = validation.message
    thread_id = validation.thread_id
    max_turns = validation.max_turns
    max_budget_usd = validation.max_budget_usd

    model = validation.model or get_user_preferred_model(user_id)

    planner_mode = getattr(validation, "planner_mode", False)
    approved_plan = getattr(validation, "approved_plan", None)
    approved_mode_change = getattr(validation, "approved_mode_change", None)
    if getattr(validation, "deep_research_toggle", False):
        planner_mode = True

    request.state.user_id = user_id

    # Defense-in-depth: with ANYLEGAL_PLANNER_MODE off (the OSS default), the
    # enter_plan_mode/exit_plan_mode tools are not registered for the LLM, so
    # the model can't request planner_mode itself. This guard catches the case
    # where a non-default frontend ships `planner_mode: true` in the request
    # body anyway.
    if planner_mode and os.getenv("ANYLEGAL_PLANNER_MODE", "disabled").lower() != "enabled":
        raise HTTPException(
            status_code=503,
            detail=(
                "Planner mode is disabled in this deployment. "
                "Set ANYLEGAL_PLANNER_MODE=enabled in .env and recreate the "
                "backend container to enable it."
            ),
        )

    guard = request.app.state.session_guard
    acquired = await guard.acquire(session_id, timeout=300)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="Another request is already running for this session"
        )

    try:

        workspace = await asyncio.to_thread(Workspace.get_or_create, user_id)

        active_doc = getattr(validation, "active_document", None)
        if active_doc and active_doc in workspace.documents:
            workspace.set_active_document(active_doc)
            logger.info(
                f"[AGENTIC_ASYNC] active_document set from request: {active_doc!r}"
            )
        elif active_doc:
            logger.info(
                f"[AGENTIC_ASYNC] active_document {active_doc!r} not in "
                f"workspace ({len(workspace.documents)} docs) — ignoring"
            )

        agent = create_agentic_chat_async(
            model=model,
            session_guard=None,
            planner_mode=planner_mode,
            approved_plan=approved_plan,
            approved_mode_change=approved_mode_change,
        )

        async def event_stream():
            try:
                async for event in agent.run_async(
                    session=workspace,
                    message=message,
                    user_id=user_id,
                    thread_id=thread_id,
                    max_turns=max_turns,
                    max_budget_usd=max_budget_usd,
                ):

                    data_json = json.dumps({**event.data, "timestamp": event.timestamp})
                    yield f"event: {event.type}\ndata: {data_json}\n\n"

                    if os.getenv("EAGER_FLUSH", "false").lower() == "true":
                        await asyncio.to_thread(flush_session_storage)

            except Exception as e:
                logger.error(f"Error in agentic stream: {e}", exc_info=True)
                error_data = json.dumps({
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                yield f"event: error\ndata: {error_data}\n\n"
            finally:

                try:
                    await asyncio.to_thread(workspace.save)
                except Exception as save_err:
                    logger.error(f"Failed to persist workspace at end of stream: {save_err}")

                await guard.release(session_id)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",                           
                "Connection": "keep-alive"
            }
        )

    except HTTPException:
        await guard.release(session_id)
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        await guard.release(session_id)
        raise HTTPException(status_code=500, detail="Internal server error")

@app.post("/api/v1/agentic/compact")
async def compact_conversation(
    request: Request,
):
    """
    Manual compaction endpoint.
    """
    _check_chat_killswitch()
    user_id = OSS_USER_ID

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    session_id = body.get("session_id")
    thread_id = body.get("thread_id")                                                   
    custom_instructions = body.get("custom_instructions")

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    guard = request.app.state.session_guard
    acquired = await guard.acquire(session_id, timeout=300)
    if not acquired:
        raise HTTPException(status_code=409, detail="Session locked")

    try:
        workspace = WorkspaceSession(user_id=user_id, session_id=session_id)

        from anylegal_oss.state import load_session_transcript
        transcript = await asyncio.to_thread(load_session_transcript, session_id)

        messages = []
        for entry in transcript:
            role = entry.get("role")
            if role in ("user", "assistant"):
                messages.append({
                    "role": role,
                    "content": entry.get("content", ""),
                })

        if not messages:
            raise HTTPException(status_code=400, detail="No messages to compact")

        from anylegal_oss.services.compaction.compactor import perform_compaction
        from anylegal_oss.state.session_state import get_session_state
        session_state = get_session_state(session_id)
        result = await perform_compaction(
            messages=messages,
            session_state=session_state,
            custom_instructions=custom_instructions,
            is_auto=False,
        )

        if result["success"]:

            if thread_id:
                try:
                    from anylegal_oss.db import async_db as _async_db
                    summary_str = ""
                    for sm in (result.get("summary_messages") or []):
                        sm_content = sm.get("content")
                        if isinstance(sm_content, str):
                            summary_str = sm_content
                        elif isinstance(sm_content, list):
                            summary_str = "\n".join(
                                (b.get("text") or "")
                                for b in sm_content
                                if isinstance(b, dict)
                            )
                        if summary_str:
                            break
                    boundary_metadata = json.dumps({
                        "pre_tokens": result.get("pre_tokens", 0),
                        "post_tokens": result.get("post_tokens", 0),
                        "is_auto": False,
                    })
                    await _async_db.save_agentic_message(
                        session_id=session_id,
                        thread_id=thread_id,
                        user_id=user_id,
                        message_type='compaction_boundary',
                        content=summary_str,
                        tool_arguments=boundary_metadata,
                    )
                except Exception as e:
                    logger.warning(f"[COMPACT] Failed to persist boundary row: {e}")

            return {
                "success": True,
                "session_id": session_id,
                "thread_id": thread_id,
                "pre_tokens": result["pre_tokens"],
                "post_tokens": result["post_tokens"],
                "summary": result["summary"],
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Compaction failed"))

    finally:
        await guard.release(session_id)

@app.post("/api/v1/agentic/sessions/switch")
async def switch_session(
    request: Request,
):
    """
    Resume an existing session. Returns the prior agentic_messages for the
    thread so the frontend can display them.

    Body: {"session_id": "...", "thread_id": "..." (optional)}
    """
    _check_chat_killswitch()
    user_id = OSS_USER_ID
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    session_id = body.get("session_id")
    thread_id = body.get("thread_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    from anylegal_oss.db import async_db
    try:
        if thread_id:
            rows = await async_db.get_agentic_thread_messages(thread_id=thread_id, limit=200)
        else:
            rows = await async_db.get_agentic_thread_messages(session_id=session_id, limit=200)
    except Exception as e:
        logger.error(f"switch_session: DB load failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load session")

    if not rows:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    public = [
        {
            "role": r.get("message_type"),
            "content": r.get("content"),
            "tool_name": r.get("tool_name"),
            "tool_call_id": r.get("tool_call_id"),
            "created_at": r.get("created_at"),
        }
        for r in rows
    ]

    return {
        "success": True,
        "session_id": session_id,
        "thread_id": thread_id,
        "message_count": len(public),
        "messages": public,
    }

@app.get("/api/v1/agentic/sessions")
async def list_sessions(
    request: Request,
):
    """
    List available session transcripts.
    """
    _check_chat_killswitch()
    from anylegal_oss.state import list_session_transcripts
    sessions = await asyncio.to_thread(list_session_transcripts)

    return {
        "sessions": sessions,
        "count": len(sessions),
    }

# For development entrypoint use `python -m uvicorn main:app` from
# backend/, or `docker compose up`. There is no `__main__` block here on
# purpose: uvicorn loads the `app` symbol directly.