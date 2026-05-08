"""
Agentic Workspace Chat — Async

Async implementation of the agentic loop for FastAPI with async/await throughout.
Parallel to the sync ``agentic_chat.py`` used by the Flask app.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

_LLM_READ_TIMEOUT = float(os.getenv("LLM_READ_TIMEOUT_SECONDS", "300"))
LLM_HTTP_TIMEOUT = httpx.Timeout(connect=30.0, read=_LLM_READ_TIMEOUT, write=30.0, pool=30.0)

_TOKENIZER = None
_TOKENIZER_NAME = "o200k_base"

def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        import tiktoken
        _TOKENIZER = tiktoken.get_encoding(_TOKENIZER_NAME)
    return _TOKENIZER

from.session import WorkspaceSession
from.tools.tool_executor import AsyncToolExecutor, ToolResult
from.tools.workspace_tools import WORKSPACE_TOOLS, get_workspace_tools

from anylegal_oss.db import async_db
from anylegal_oss.services.compaction.compactor import perform_compaction
from anylegal_oss.state.transcript import flush_session_storage, record_transcript

def _default_system_prompt(self) -> str:
        """Load system prompt from prompts/system_prompt.md file."""
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "system_prompt.md"
        )
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt = f.read()

            # for the schema, and the "CRITICAL: Skills Contain the Required

            try:
                from.skills.skill_loader import create_skill_loader
                loader = create_skill_loader()
                skills = loader.discover_skills()

                if skills:
                    skills_section = "\n## Available Skills\n\n"
                    for skill in skills:
                        desc = skill.description or skill.name
                        skills_section += f"- **{skill.name}** — {desc}\n"
                    skills_section += (
                        "\n"
                        "Invoke any of these via the `Skill` tool: "
                        "`Skill(skill=\"<name>\")`. The full procedure is "
                        "returned as the tool result — follow it on the next "
                        "turn. **Do NOT read the SKILL.md file** via "
                        "`read_document` — use the `Skill` tool instead so "
                        "the tool pool is correctly scoped.\n"
                    )

                    prompt = prompt.rstrip() + skills_section
            except Exception as e:
                logger.warning(f"Failed to load skills for system prompt: {e}")

            return prompt
        except FileNotFoundError:
            logger.warning(f"System prompt file not found at {prompt_path}, using minimal fallback")
            return (
                "You are an expert legal AI assistant in AnyLegal's agentic workspace. "
                "Help users with contract review, drafting, research, and document editing."
            )

logger = logging.getLogger(__name__)

@dataclass
class AgenticEvent:
    """Event emitted during agentic loop execution."""
    type: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type": self.type,
            "data": self.data,
            "timestamp": self.timestamp
        }

class AgenticWorkspaceChatAsync:
    """
    Async version of AgenticWorkspaceChat with external session guard and state tracking.
    Designed for FastAPI with true async/await.
    """

    MAX_ITERATIONS = 50
    MAX_TOOL_CALLS_PER_ITERATION = 20
    CONTEXT_WARN_THRESHOLD = 70     
    CONTEXT_CRITICAL_THRESHOLD = 85     

    def __init__(
        self,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        session_guard = None,                     
        planner_mode: bool = False,
        approved_plan: Optional[Dict[str, Any]] = None,
        approved_mode_change: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize async agentic chat.

        Args:
            model: LLM model to use (defaults to env CHAT_MODEL)
            system_prompt: Optional system prompt override
            session_guard: External async session guard (injected)
            planner_mode: Run the agent in plan-and-execute mode (Planner service).
                The planner template is selected automatically from the session's
                loaded skills — e.g. a prior ``read_document("Skills/research/
                SKILL.md")`` in the thread routes to the ``legal_research``
                template. See ``_detect_planner_template``.
            approved_plan: Plan JSON previously emitted by the planner and
                approved by the user, echoed back to skip re-planning and
                execute directly. Implements ``exit_plan_mode``
                approval flow where the plan re-enters conversation context
                on approval. When None (default) and ``planner_mode=True``,
                the agent emits a plan and returns without executing.
        """
        from anylegal_oss.core.pricing import get_model_registry
        self.model = model or os.getenv("CHAT_MODEL") or get_model_registry().get_default_model()
        self.planner_mode = planner_mode
        self._approved_plan = approved_plan
        self._approved_mode_change = approved_mode_change
        logger.info(
            f"[AGENTIC_ASYNC] Initialized with model: {self.model}, "
            f"planner_mode={self.planner_mode}"
        )
        self.system_prompt = system_prompt
        self._cancelled = False
        self._session_guard = session_guard
        self._enable_streaming = os.getenv("AGENTIC_STREAMING", "true").lower() == "true"

        self._session_id: Optional[str] = None
        self._session_state = None
        self._workspace: Optional[WorkspaceSession] = None

        self._turn_count = 0
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost_usd = 0.0

        self._truncation_retries_used = 0
        self.MAX_TRUNCATION_RETRIES = 4

    async def run_async(
        self,
        session: WorkspaceSession,
        message: str,
        user_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        max_turns: int = 50,
        max_budget_usd: Optional[float] = None,
        image_attachments: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[AgenticEvent, None]:
        """
        Run the agentic loop asynchronously.

        Args:
            session: Workspace session
            message: User's message
            user_id: User ID for billing
            thread_id: Thread ID for persistence
            max_turns: Maximum iterations (default 50)
            max_budget_usd: Optional budget limit
            image_attachments: Optional images

        Yields:
            AgenticEvent objects for SSE streaming
        """
        self._session_id = session.session_id
        self._workspace = session

        from anylegal_oss.state.session_state import get_session_state
        self._session_state = get_session_state(self._session_id)

        mode_change_tool_result = None
        if self._approved_mode_change:
            change = self._approved_mode_change
            approved = bool(change.get("approved"))
            target_mode = change.get("mode") or "plan"
            if approved and target_mode == "plan":
                self._session_state.mode = "plan"

                from anylegal_oss.workspace.tools.mode_tools import PLAN_MODE_ENTRY_RESULT
                mode_change_tool_result = (
                    change.get("tool_call_id"),
                    PLAN_MODE_ENTRY_RESULT,
                )
            else:

                mode_change_tool_result = (
                    change.get("tool_call_id"),
                    "User declined plan mode. Continue reactively — answer "
                    "directly or use tools as needed.",
                )

        approved_plan_tool_result = None
        if self._approved_plan:
            plan_payload = self._approved_plan
            plan_text = plan_payload.get("plan_text") if isinstance(plan_payload, dict) else None
            if not plan_text and isinstance(plan_payload, dict) and plan_payload.get("steps"):

                lines = []
                if plan_payload.get("goal"):
                    lines.append(f"**Goal:** {plan_payload['goal']}")
                for i, step in enumerate(plan_payload.get("steps") or [], start=1):
                    if isinstance(step, dict) and step.get("description"):
                        lines.append(f"{i}. {step['description']}")
                plan_text = "\n".join(lines) if lines else None
            if plan_text:
                self._session_state.mode = "default"

                self._session_state.plan_already_approved = True
                tool_call_id = plan_payload.get("tool_call_id") if isinstance(plan_payload, dict) else None

                approval_body = (
                    "User has approved your plan. Begin executing it now with the full tool pool.\n\n"
                    "- Use the `todo_write` tool to track progress through the plan steps as you go, if applicable.\n"
                    "- Start with the first step. Use tool calls to gather information; produce a final answer at the end.\n\n"
                    "**Output rules for this turn (MANDATORY):**\n"
                    "- Cite every factual claim inline using [[N]](URL). Start numbering at [1] for this response.\n"
                    "- End the response with a ## Sources section listing each URL in order.\n"
                    "- If a tool errored during exploration, do not invent a source — say so and use only sources you actually fetched.\n"
                    "- Do NOT use markdown horizontal rules (--- or ***) as section dividers.\n\n"
                    f"## Approved Plan\n\n{plan_text}"
                )
                approved_plan_tool_result = (tool_call_id, approval_body)

        if self._session_guard:
            acquired = await self._session_guard.acquire(self._session_id, timeout=300)
            if not acquired:
                yield AgenticEvent(
                    type="error",
                    data={"error": "Session is already running"}
                )
                return

        try:

            self._cancelled = False
            self._turn_count = 0
            self._total_prompt_tokens = 0
            self._total_completion_tokens = 0
            self._total_cost_usd = 0.0

            from anylegal_oss.workspace.tools.skill_tool import reset_skill_scope
            reset_skill_scope(self._session_state)

            yield AgenticEvent(
                type="start",
                data={
                    "session_id": self._session_id,
                    "workspace_id": session.session_id,
                    "thread_id": thread_id,
                    "message": message[:100] + "..." if len(message) > 100 else message,
                    "model": self.model,
                    "streaming": self._enable_streaming,
                }
            )

            user_msg = {
                "role": "user",
                "content": message,
                "session_id": self._session_id,
                "thread_id": thread_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            record_transcript([user_msg], session_id=self._session_id)

            try:
                await async_db.save_agentic_message(
                    session_id=self._session_id,
                    thread_id=thread_id,
                    user_id=user_id or 0,
                    message_type='user',
                    content=message,
                    model_used=self.model,
                )
            except Exception as e:
                logger.warning(f"[AGENTIC] Failed to persist user message: {e}")

            messages = await self._build_initial_messages(
                session,
                message,
                thread_id=thread_id,
                user_id=user_id or 0,
            )

            if mode_change_tool_result is not None:
                tool_call_id, content = mode_change_tool_result
                resolved_tcid = tool_call_id or "enter_plan_mode_approval"
                messages.insert(-1, {
                    "role": "tool",
                    "tool_call_id": resolved_tcid,
                    "content": content,
                })
                try:
                    await async_db.save_agentic_message(
                        session_id=self._session_id,
                        thread_id=thread_id,
                        user_id=user_id or 0,
                        message_type='tool_result',
                        tool_name='enter_plan_mode',
                        tool_call_id=resolved_tcid,
                        content=content,
                        model_used=self.model,
                    )
                except Exception as e:
                    logger.warning(f"[AGENTIC] Failed to persist enter_plan_mode tool_result: {e}")
            if approved_plan_tool_result is not None:
                tool_call_id, content = approved_plan_tool_result
                resolved_tcid = tool_call_id or "exit_plan_mode_approval"
                messages.insert(-1, {
                    "role": "tool",
                    "tool_call_id": resolved_tcid,
                    "content": content,
                })
                try:
                    await async_db.save_agentic_message(
                        session_id=self._session_id,
                        thread_id=thread_id,
                        user_id=user_id or 0,
                        message_type='tool_result',
                        tool_name='exit_plan_mode',
                        tool_call_id=resolved_tcid,
                        content=content,
                        model_used=self.model,
                    )
                except Exception as e:
                    logger.warning(f"[AGENTIC] Failed to persist exit_plan_mode tool_result: {e}")

            # TODO checklist), then walk the steps one at a time with a

            plan = None
            if self.planner_mode:
                async for evt in self._plan_and_execute(
                    session=session, user_id=user_id or 0, thread_id=thread_id,
                    user_message=message, messages=messages,
                    max_turns=max_turns, max_budget_usd=max_budget_usd,
                ):
                    yield evt

                yield AgenticEvent(
                    type="end",
                    data={
                        "session_id": self._session_id,
                        "workspace_id": session.session_id,
                        "thread_id": thread_id,
                        "total_cost_usd": self._total_cost_usd,
                        "total_prompt_tokens": self._total_prompt_tokens,
                        "total_completion_tokens": self._total_completion_tokens,
                        "iterations": self._turn_count,
                        "planner_mode": True,
                        "workers_spawned": 0,
                    },
                )
                return

            iteration = 0
            while iteration < max_turns:
                iteration += 1
                self._turn_count = iteration

                if self._cancelled:
                    yield AgenticEvent(
                        type="text_chunk",
                        data={"content": "[Cancelled by user]"}
                    )
                    break

                if max_budget_usd and self._total_cost_usd >= max_budget_usd:
                    yield AgenticEvent(
                        type="error",
                        data={"error": f"Budget limit ${max_budget_usd} exceeded"}
                    )
                    break

                ctx_tokens = self._estimate_tokens(messages)
                ctx_pct = self._context_usage_pct(ctx_tokens, self.model)

                if ctx_pct >= self.CONTEXT_CRITICAL_THRESHOLD:
                    logger.warning(f"[AGENTIC] Context CRITICAL: {ctx_tokens:,} tokens ({ctx_pct:.0f}%)")
                elif ctx_pct >= self.CONTEXT_WARN_THRESHOLD:
                    logger.warning(f"[AGENTIC] Context HIGH: {ctx_tokens:,} tokens ({ctx_pct:.0f}%)")
                else:
                    logger.info(f"[AGENTIC] Context: {ctx_tokens:,} tokens ({ctx_pct:.0f}%), iteration {iteration}")

                if iteration > 2 and ctx_pct >= self.CONTEXT_CRITICAL_THRESHOLD:
                    yield AgenticEvent(
                        type="system_message",
                        data={"content": f"Context at {ctx_pct:.0f}% — compacting prior conversation..."}
                    )
                    pre_len = len(messages)
                    messages = await self._auto_compact(messages, thread_id=thread_id, user_id=user_id)
                    yield AgenticEvent(
                        type="system_message",
                        data={"content": f"Compacted {pre_len} → {len(messages)} messages."}
                    )

                accumulated_content = ""
                tool_calls: List[Dict[str, Any]] = []
                usage: Optional[Dict[str, Any]] = None
                finish_reason: Optional[str] = None
                async for evt in self._call_llm_streaming(messages):
                    evt_type = evt.get("type")
                    if evt_type == "content":
                        delta_text = evt.get("delta") or ""
                        if delta_text:

                            plan_mode_active = (
                                self._session_state is not None
                                and getattr(self._session_state, "mode", "default") == "plan"
                            )
                            if plan_mode_active:
                                yield AgenticEvent(
                                    type="thinking",
                                    data={"content": delta_text}
                                )
                            else:
                                yield AgenticEvent(
                                    type="text_chunk",
                                    data={"content": delta_text}
                                )
                    elif evt_type == "reasoning":

                        accumulated = evt.get("accumulated") or evt.get("delta") or ""
                        if accumulated:
                            yield AgenticEvent(
                                type="thinking",
                                data={"content": accumulated}
                            )
                    elif evt_type == "done":
                        accumulated_content = evt.get("content", "") or ""
                        tool_calls = evt.get("tool_calls") or []
                        usage = evt.get("usage")
                        finish_reason = evt.get("finish_reason")

                if usage:
                    self._total_prompt_tokens += usage.get("prompt_tokens", 0)
                    self._total_completion_tokens += usage.get("completion_tokens", 0)
                    self._total_cost_usd += usage.get("cost", 0.0)

                    from anylegal_oss.state.session_state import ModelUsage
                    model_usage = ModelUsage(
                        input_tokens=usage.get("prompt_tokens", 0),
                        output_tokens=usage.get("completion_tokens", 0),
                        cost=usage.get("cost", 0.0),
                    )
                    self._session_state.accumulate_cost(self.model, model_usage)

                if tool_calls:

                    parse_failed_calls = [tc for tc in tool_calls if tc.get("parse_failed")]
                    if parse_failed_calls:

                        openai_all = [
                            {
                                "id": tc.get("id") or f"call_{iteration}_{tc.get('index', 0)}",
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc.get("arguments", {}))
                                    if isinstance(tc.get("arguments"), dict)
                                    else (tc.get("arguments") or "{}"),
                                },
                            }
                            for tc in tool_calls
                        ]
                        messages.append({
                            "role": "assistant",
                            "content": accumulated_content or None,
                            "tool_calls": openai_all,
                        })
                        for tc in parse_failed_calls:
                            tool_call_id = tc.get("id") or f"call_{iteration}_{tc.get('index', 0)}"
                            raw_preview = (tc.get("raw_arguments") or "")[:120]
                            error_msg = (
                                f"Tool call arguments for '{tc['name']}' could "
                                f"not be parsed as JSON — the provider likely "
                                f"truncated the response mid-stream. Received: "
                                f"{raw_preview!r}. Retry the call with valid "
                                f"JSON arguments; keep them minimal."
                            )
                            yield AgenticEvent(
                                type="tool_call",
                                data={
                                    "tool_name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "tool_call_id": tool_call_id,
                                    "streaming": False,
                                }
                            )
                            yield AgenticEvent(
                                type="tool_result",
                                data={
                                    "tool_name": tc["name"],
                                    "tool_call_id": tool_call_id,
                                    "success": False,
                                    "result": {},
                                    "error": error_msg,
                                    "execution_time_ms": 0.0,
                                },
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": error_msg,
                            })

                        tool_calls = [tc for tc in tool_calls if not tc.get("parse_failed")]
                        assistant_msg_already_appended = True
                        if not tool_calls:

                            continue
                    else:
                        assistant_msg_already_appended = False

                    current_mode_for_validation = (
                        getattr(self._session_state, "mode", "default")
                        if self._session_state else "default"
                    )
                    invalid_exit_calls = [
                        tc for tc in tool_calls
                        if tc["name"] == "exit_plan_mode" and current_mode_for_validation != "plan"
                    ]
                    if invalid_exit_calls:
                        from anylegal_oss.workspace.tools.mode_tools import EXIT_PLAN_MODE_NOT_IN_PLAN_MODE_ERROR
                        for tc in invalid_exit_calls:
                            tool_call_id = f"call_{iteration}_{tc.get('index', 0)}"
                            yield AgenticEvent(
                                type="tool_call",
                                data={
                                    "tool_name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "tool_call_id": tool_call_id,
                                    "streaming": False,
                                }
                            )
                            yield AgenticEvent(
                                type="tool_result",
                                data={
                                    "tool_name": tc["name"],
                                    "tool_call_id": tool_call_id,
                                    "success": False,
                                    "result": {},
                                    "error": EXIT_PLAN_MODE_NOT_IN_PLAN_MODE_ERROR,
                                    "execution_time_ms": 0.0,
                                },
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call_id,
                                "content": EXIT_PLAN_MODE_NOT_IN_PLAN_MODE_ERROR,
                            })

                        tool_calls = [tc for tc in tool_calls if tc not in invalid_exit_calls]

                    for tc in tool_calls:
                        if tc["name"] in ("enter_plan_mode", "exit_plan_mode"):
                            tool_call_id = f"call_{iteration}_{tc.get('index', 0)}"
                            yield AgenticEvent(
                                type="tool_call",
                                data={
                                    "tool_name": tc["name"],
                                    "arguments": tc["arguments"],
                                    "tool_call_id": tool_call_id,
                                    "streaming": False,
                                    "awaiting_approval": True,
                                }
                            )

                            try:
                                args_json = json.dumps(tc["arguments"]) if isinstance(tc["arguments"], dict) else str(tc.get("arguments", ""))
                                await async_db.save_agentic_message(
                                    session_id=self._session_id,
                                    thread_id=thread_id,
                                    user_id=user_id or 0,
                                    message_type='tool_call',
                                    tool_name=tc["name"],
                                    tool_call_id=tool_call_id,
                                    tool_arguments=args_json,
                                    model_used=self.model,
                                )
                            except Exception as e:
                                logger.warning(f"[AGENTIC] Failed to persist mode-transition tool_call: {e}")

                            yield AgenticEvent(
                                type="end",
                                data={
                                    "session_id": self._session_id,
                                    "workspace_id": session.session_id,
                                    "thread_id": thread_id,
                                    "total_cost_usd": self._total_cost_usd,
                                    "total_prompt_tokens": self._total_prompt_tokens,
                                    "total_completion_tokens": self._total_completion_tokens,
                                    "iterations": iteration,
                                    "awaiting_approval": True,
                                    "approval_kind": tc["name"],
                                }
                            )
                            return

                    for tc in tool_calls:
                        tool_call_id = f"call_{iteration}_{tc.get('index', 0)}"
                        yield AgenticEvent(
                            type="tool_call",
                            data={
                                "tool_name": tc["name"],
                                "arguments": tc["arguments"],
                                "tool_call_id": tool_call_id,
                                "streaming": False,
                            }
                        )

                        try:
                            args_json = (
                                json.dumps(tc["arguments"])
                                if isinstance(tc["arguments"], dict)
                                else str(tc.get("arguments", ""))
                            )
                            await async_db.save_agentic_message(
                                session_id=self._session_id,
                                thread_id=thread_id,
                                user_id=user_id or 0,
                                message_type='tool_call',
                                tool_name=tc["name"],
                                tool_call_id=tool_call_id,
                                tool_arguments=args_json,
                                model_used=self.model,
                            )
                        except Exception as e:
                            logger.warning(f"[AGENTIC] Failed to persist tool_call: {e}")

                        result = await self._execute_tool(tc)
                        yield AgenticEvent(
                            type="tool_result",
                            data={
                                "tool_name": tc["name"],
                                "tool_call_id": tool_call_id,
                                "success": result.success,
                                "result": result.result,
                                "error": result.error,
                                "execution_time_ms": result.execution_time_ms,
                            }
                        )

                        if result.success and isinstance(result.result, dict):
                            created: list[dict] = []
                            if tc["name"] == "create_document":
                                doc_path = result.result.get("document_created") or result.result.get("path")
                                if doc_path:
                                    created.append({
                                        "path": doc_path,
                                        "description": result.result.get("description", ""),
                                        "format": result.result.get("format", "md"),
                                        "has_docx": bool(result.result.get("has_docx")),
                                    })
                            elif tc["name"] == "run_code":
                                for entry in result.result.get("files_created") or []:
                                    if not (entry.get("added_to_workspace") and entry.get("path")):
                                        continue
                                    entry_type = entry.get("type") or ""
                                    fmt = Path(entry["path"]).suffix.lstrip(".").lower() or entry_type or "md"
                                    created.append({
                                        "path": entry["path"],
                                        "description": "Generated by run_code",
                                        "format": fmt,
                                        "has_docx": entry_type == "docx" or fmt == "docx",
                                    })

                            for doc in created:
                                yield AgenticEvent(
                                    type="document_created",
                                    data={
                                        "path": doc["path"],
                                        "description": doc["description"],
                                        "workspace_id": session.session_id,
                                        "format": doc["format"],
                                        "has_docx": doc["has_docx"],
                                    },
                                )

                        try:
                            result_content = result.result if result.success else (result.error or "Error")
                            if result_content and len(str(result_content)) > 10000:
                                result_content = str(result_content)[:10000] + "... [truncated]"
                            await async_db.save_agentic_message(
                                session_id=self._session_id,
                                thread_id=thread_id,
                                user_id=user_id or 0,
                                message_type='tool_result',
                                content=str(result_content),
                                tool_name=tc["name"],
                                tool_call_id=tool_call_id,
                            )
                        except Exception as e:
                            logger.warning(f"[AGENTIC] Failed to persist tool_result: {e}")

                        if result.success:
                            tool_content = json.dumps(result.result)
                        elif isinstance(result.result, dict):
                            payload = dict(result.result)
                            if result.error and not payload.get("error"):
                                payload["error"] = result.error
                            tool_content = json.dumps(payload)
                        else:
                            tool_content = result.error or ""
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": tool_content,
                        })

                    if not assistant_msg_already_appended:
                        openai_tool_calls = [
                            {
                                "id": tc.get("id") or f"call_{iteration}_{tc.get('index', 0)}",
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": json.dumps(tc.get("arguments", {}))
                                    if isinstance(tc.get("arguments"), dict)
                                    else (tc.get("arguments") or "{}"),
                                },
                            }
                            for tc in tool_calls
                        ]
                        messages.append({
                            "role": "assistant",
                            "content": accumulated_content or None,
                            "tool_calls": openai_tool_calls,
                        })
                else:

                    is_empty = not (accumulated_content and accumulated_content.strip())
                    if is_empty and finish_reason in ("length", "stop"):

                        async for ev in self._handle_empty_truncated_response(
                            usage=usage,
                            thread_id=thread_id,
                            user_id=user_id,
                            finish_reason=finish_reason,
                        ):
                            yield ev
                        if self._truncation_retries_used <= self.MAX_TRUNCATION_RETRIES:

                            continue

                        break

                    if accumulated_content and accumulated_content.strip():
                        try:
                            await async_db.save_agentic_message(
                                session_id=self._session_id,
                                thread_id=thread_id,
                                user_id=user_id or 0,
                                message_type='assistant',
                                content=accumulated_content,
                                model_used=self.model,
                                tokens_used=self._total_prompt_tokens + self._total_completion_tokens,
                                cost=self._total_cost_usd,
                            )
                        except Exception as e:
                            logger.warning(f"[AGENTIC] Failed to persist final assistant message: {e}")
                    break

                assistant_msg = {
                    "role": "assistant",
                    "content": accumulated_content,
                    "tool_calls": tool_calls if tool_calls else None,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                record_transcript([assistant_msg], session_id=self._session_id)

                if tool_calls and accumulated_content and accumulated_content.strip():
                    try:
                        await async_db.save_agentic_message(
                            session_id=self._session_id,
                            thread_id=thread_id,
                            user_id=user_id or 0,
                            message_type='assistant',
                            content=accumulated_content,
                            model_used=self.model,
                        )
                    except Exception as e:
                        logger.warning(f"[AGENTIC] Failed to persist assistant message: {e}")

                if os.getenv("EAGER_FLUSH", "false").lower() == "true":
                    flush_session_storage()

            yield AgenticEvent(
                type="end",
                data={
                    "session_id": self._session_id,
                    "workspace_id": session.session_id,
                    "thread_id": thread_id,
                    "total_cost_usd": self._total_cost_usd,
                    "total_prompt_tokens": self._total_prompt_tokens,
                    "total_completion_tokens": self._total_completion_tokens,
                    "iterations": iteration,
                }
            )

        except Exception as e:
            logger.error(f"Agentic loop error: {e}", exc_info=True)
            yield AgenticEvent(
                type="error",
                data={"error": str(e)}
            )
            yield AgenticEvent(
                type="end",
                data={"session_id": self._session_id, "workspace_id": session.session_id, "error": True}
            )
        finally:

            if self._session_guard:
                await self._session_guard.release(self._session_id)

    async def _build_initial_messages(
        self,
        session: WorkspaceSession,
        user_message: str,
        thread_id: Optional[str] = None,
        user_id: int = 0,
    ) -> List[Dict]:
        """Build initial message list for LLM, loading prior thread history if resuming."""
        messages: List[Dict] = []

        system_prompt = self.system_prompt or self._default_system_prompt()

        try:
            cascade = session.get_anylegal_cascade(
                document_path=session.active_document
            )
            if cascade:
                parts = [
                    f"### Instructions ({label}):\n{content}"
                    for label, content in cascade
                ]
                system_prompt += (
                    "\n\n## User Instructions (anylegal.md cascade):\n"
                    + "\n\n".join(parts)
                )
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] anylegal cascade load failed: {e}")

        try:
            from.memory_layer import build_memory_layer
            memory_block = build_memory_layer(
                session=session,
                workspace_id=getattr(session, 'session_id', '') or '',
                active_doc_path=session.active_document,
                user_id=user_id,
            )
            if memory_block:
                system_prompt += "\n\n" + memory_block
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] memory layer build failed: {e}")

        try:
            playbook_manifest = session.build_playbook_manifest()
            if playbook_manifest:
                system_prompt += f"\n\n{playbook_manifest}"
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] playbook manifest load failed: {e}")

        try:
            template_files = session.get_template_files()
            if template_files:
                tmpl_list = "\n".join(
                    f"- `{t['path']}` (read-only)" for t in template_files
                )
                system_prompt += (
                    f"\n\n## Available Templates (user-uploaded, read-only for agent):\n"
                    f"{tmpl_list}\n"
                    f"Use `read_document` to read a template. Do NOT write to Templates/."
                )
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] templates list failed: {e}")

        try:
            visible_wf = {
                path: content for path, content in session.workspace_files.items()
                if not path.endswith("anylegal.md") and content and content.strip()
            }
            if visible_wf:
                wf_list = "\n".join(f"- {path}" for path in visible_wf)
                system_prompt += f"\n\n## Workspace Files (readable/editable via tools):\n{wf_list}"
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] workspace files list failed: {e}")

        system_prompt += f"\n\n## Current Date\nToday is {datetime.now().strftime('%d %B %Y')}."

        try:
            if session.documents:
                def _doc_format_label(doc, path):
                    if doc.mime_type and doc.mime_type.startswith('image/'):
                        return 'IMAGE — visible in attached messages'
                    if doc.docx_blob:
                        return 'DOCX'
                    ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
                    if ext in ('pdf', 'xlsx', 'xls', 'pptx', 'ppt'):
                        return ext.upper()
                    return 'HTML'

                doc_list = "\n".join([
                    f"- {path}: {doc.description or 'No description'} "
                    f"({_doc_format_label(doc, path)})"
                    for path, doc in session.documents.items()
                ])
                system_prompt += f"\n\n## Current Workspace Documents:\n{doc_list}"

                if session.active_document:
                    is_reviewable = session.active_document in session.documents
                    system_prompt += f"\n\nActive document: {session.active_document}"
                    if is_reviewable:
                        system_prompt += (
                            "\nWhen the user says 'this', 'the document', 'this agreement', or similar "
                            "references without specifying a name, they mean the active document. "
                            "Read and work with it directly — do NOT ask which document."
                        )
                    else:
                        system_prompt += (
                            f"\n\n**Note:** The active document '{session.active_document}' is NOT a contract or "
                            f"document to review — it is an instructions/playbook/template/reference file. "
                            f"If the user asks to review, draft, compare, or edit a document, you MUST ask which "
                            f"document from the workspace they want to work with. Do NOT review or analyze the "
                            f"active file itself. List the available documents above and ask the user to pick one."
                        )

            if session.context:
                ctx_str = ", ".join(f"{k}: {v}" for k, v in session.context.items())
                system_prompt += f"\n\n## Session Context:\n{ctx_str}"
        except Exception as e:
            logger.warning(f"[AGENTIC_ASYNC] workspace context assembly failed: {e}")

        from anylegal_oss.workspace.tools.todo_tool import TODO_WRITE_GUIDANCE
        system_prompt = f"{system_prompt}\n\n## Progress Tracking\n\n{TODO_WRITE_GUIDANCE}"

        from anylegal_oss.workspace.tools.mode_tools import (
            PLAN_MODE_GUIDANCE, LEGAL_RESEARCH_PLAN_HINT,
        )
        current_mode = getattr(self._session_state, "mode", "default") if self._session_state else "default"
        if current_mode == "plan":
            system_prompt = f"{system_prompt}\n\n## Plan Mode\n\n{PLAN_MODE_GUIDANCE}"

            system_prompt = f"{system_prompt}\n\n### Legal research\n\n{LEGAL_RESEARCH_PLAN_HINT}"

        messages.append({
            "role": "system",
            "content": system_prompt,
        })

        if thread_id:
            try:
                prior = await async_db.get_agentic_thread_messages(
                    thread_id=thread_id,
                    limit=200,
                )

                system_prefix_len = len(messages)
                id_map: Dict[str, str] = {}
                replayed_tool_events = 0
                boundaries_seen = 0
                for row in prior:
                    mtype = row.get("message_type")
                    content = row.get("content")
                    if mtype == "compaction_boundary":

                        del messages[system_prefix_len:]
                        id_map = {}                                              
                        if content:
                            messages.append({"role": "user", "content": content})
                        boundaries_seen += 1
                    elif mtype == "user":
                        if content:
                            messages.append({"role": "user", "content": content})
                    elif mtype == "assistant":
                        if content:
                            messages.append({"role": "assistant", "content": content})
                    elif mtype == "tool_call":
                        old_id = row.get("tool_call_id") or ""
                        new_id = f"replay_{uuid.uuid4().hex[:12]}"
                        if old_id:
                            id_map[old_id] = new_id
                        tool_name = row.get("tool_name") or ""
                        tool_args = row.get("tool_arguments") or "{}"
                        if not tool_name:
                            continue
                        messages.append({
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [{
                                "id": new_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_args,
                                },
                            }],
                        })
                        replayed_tool_events += 1
                    elif mtype == "tool_result":
                        old_id = row.get("tool_call_id") or ""
                        new_id = id_map.get(old_id)
                        if not new_id:

                            continue
                        messages.append({
                            "role": "tool",
                            "tool_call_id": new_id,
                            "content": content or "",
                        })
                        replayed_tool_events += 1
                logger.info(
                    f"[AGENTIC] Resumed thread {thread_id}: loaded {len(prior)} "
                    f"rows ({replayed_tool_events} tool events replayed, "
                    f"{boundaries_seen} compaction boundaries)"
                )
            except Exception as e:
                logger.warning(f"[AGENTIC] Failed to load thread {thread_id} history: {e}")

        messages.append({
            "role": "user",
            "content": user_message,
        })

        return messages

    def _default_system_prompt(self) -> str:
        """Load system prompt from prompts/system_prompt.md file."""
        prompt_path = os.path.join(
            os.path.dirname(__file__), "prompts", "system_prompt.md"
        )
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"System prompt file not found at {prompt_path}, using minimal fallback")
            return "You are an expert legal AI assistant in AnyLegal's agentic workspace. Help users with contract review, drafting, research, and document editing."

    def _count_tokens(self, text: str) -> int:
        """
        Count tokens in a string using a real BPE tokenizer.

        Why not len(text)//4: that heuristic averages 0.25 tok/char for
        ASCII English and falls apart on high-entropy bytes. Binary content
        accidentally injected as text (e.g. a PDF body that wasn't decoded)
        can tokenize at ~1.87 tok/char at the provider — under-reporting
        local token counts by an order of magnitude. Compaction's threshold
        won't fire when the local view is wrong by that much.

        We use tiktoken's o200k_base (the GPT-4o family encoder). It's not
        the exact tokenizer for every model — Kimi K2 uses a DeepSeek-derived
        tokenizer, Claude uses its own — but cross-model error is ~10–20%,
        which is fine for context-pressure decisions. Critically, o200k_base
        tokenizes high-entropy bytes the same way other modern BPEs do, so
        the binary-garbage failure mode is correctly caught.
        """
        try:
            return len(_get_tokenizer().encode(text or "", disallowed_special=()))
        except Exception:

            return max(0, len(text or "") // 3)

    def _estimate_tokens(self, messages: List[Dict]) -> int:
        """
        Estimate total tokens for a chat-completion message list.

        Counts content (str or Anthropic-style content blocks) AND tool_calls
        (function name + arguments JSON) AND tool_call_id strings on tool
        messages. The previous implementation counted only `content`, which
        meant tool-heavy iterations underreported by however many JSON-arg
        bytes the model emitted.

        Adds a small per-message overhead (4 tokens) to approximate the
        chat-completions message-framing overhead — matches OpenAI's published
        guidance for cl100k/o200k.
        """
        total = 0
        for msg in messages:
            total += 4                                

            content = msg.get("content")
            if isinstance(content, str):
                total += self._count_tokens(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "") or ""
                        total += self._count_tokens(text)

            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                if isinstance(tc, dict):
                    fn = tc.get("function") or {}
                    total += self._count_tokens(fn.get("name", "") or "")
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        total += self._count_tokens(args)
                    elif args is not None:
                        total += self._count_tokens(json.dumps(args))

            tcid = msg.get("tool_call_id")
            if tcid:
                total += self._count_tokens(tcid)

        return total

    def _context_usage_pct(self, tokens: int, model: str) -> float:
        """
        Compute context-window usage percentage against the model's real
        window from the model registry. Falls back to 200K for unknown
        models (most modern models exceed this; the underestimate is safer
        than overestimating headroom).

        Previously hardcoded to 200K, which under-reports context pressure
        for any model with a larger window — Kimi K2.6 (262K), Gemini 1.5/2.5
        (1M-2M), Claude Sonnet 4 (200K-1M depending on tier). Combine that
        with a broken token estimator (above) and the local view can lag
        actual context-used by tens of percentage points.
        """
        try:
            from anylegal_oss.core.pricing import get_model_registry
            info = get_model_registry().get_model(model)
            context_size = info.context_window if info and info.context_window else 200_000
        except Exception:
            context_size = 200_000
        if context_size <= 0:
            context_size = 200_000
        return (tokens / context_size) * 100

    async def _handle_empty_truncated_response(
        self,
        usage: Optional[Dict[str, Any]],
        thread_id: Optional[str],
        user_id: Optional[int],
        finish_reason: Optional[str] = None,
    ) -> AsyncGenerator[AgenticEvent, None]:
        """
        Recover from an empty stream — either finish_reason=length (provider
        truncated, no content + no tool_calls) or finish_reason=stop (model
        voluntarily stopped with all output stuck in the reasoning channel).

        First N attempts (N = MAX_TRUNCATION_RETRIES): emit a system_message
        and bump the counter. The caller will `continue` the loop, which
        re-issues the request through OpenRouter — usually onto a different
        provider or after the transient hiccup clears.

        After retries are spent: synthesize a visible assistant message,
        stream it as text_chunk so the UI renders it, persist via
        save_agentic_message so the thread isn't a ghost, and let the
        caller break.
        """
        prompt_tokens = (usage or {}).get("prompt_tokens", 0) or 0
        completion_tokens = (usage or {}).get("completion_tokens", 0) or 0

        self._truncation_retries_used += 1
        if self._truncation_retries_used <= self.MAX_TRUNCATION_RETRIES:
            logger.warning(
                f"[AGENTIC] empty stream finish_reason={finish_reason} "
                f"(prompt={prompt_tokens} completion={completion_tokens}); "
                f"retry {self._truncation_retries_used}/{self.MAX_TRUNCATION_RETRIES}"
            )

            return

        user_message = "No response from the model provider. Try again."

        logger.warning(
            f"[AGENTIC] empty stream finish_reason={finish_reason} — retry budget spent "
            f"(prompt={prompt_tokens} completion={completion_tokens}); "
            f"surfacing user-visible failure"
        )

        yield AgenticEvent(
            type="text_chunk",
            data={"content": user_message},
        )

        try:
            await async_db.save_agentic_message(
                session_id=self._session_id,
                thread_id=thread_id,
                user_id=user_id or 0,
                message_type='assistant',
                content=user_message,
                model_used=self.model,
                tokens_used=self._total_prompt_tokens + self._total_completion_tokens,
                cost=self._total_cost_usd,
            )
        except Exception as e:
            logger.warning(f"[AGENTIC] Failed to persist truncation-failure message: {e}")

    _PLAN_TOOL_CALL_ID = "plan-tool-call"
    _PLAN_TOOL_NAME = "update_plan"

    async def _emit_plan_state(self, plan) -> AsyncGenerator[AgenticEvent, None]:
        """Emit a synthetic tool_call + tool_result carrying the current plan."""
        payload = plan.to_dict()
        yield AgenticEvent(
            type="tool_call",
            data={
                "tool_name": self._PLAN_TOOL_NAME,
                "arguments": payload,
                "tool_call_id": self._PLAN_TOOL_CALL_ID,
                "streaming": False,
            },
        )
        yield AgenticEvent(
            type="tool_result",
            data={
                "tool_name": self._PLAN_TOOL_NAME,
                "tool_call_id": self._PLAN_TOOL_CALL_ID,
                "success": True,
                "result": payload,
                "error": None,
                "execution_time_ms": 0.0,
            },
        )

    _RESEARCH_SKILL_PATH = "Skills/research/SKILL.md"

    def _session_loaded_research_skill(self, messages: List[Dict]) -> bool:
        """
        Return True if the research skill was invoked anywhere in this thread.

        Detects both invocation paths (transition compatibility):
        - ``Skill(skill="research")`` — current Anthropic/convention path.
        - ``read_document("Skills/research/SKILL.md")`` — legacy path,
          honored until the legacy path is removed.

        Looks at assistant messages' ``tool_calls`` (live-run shape) and at
        DB-rehydrated ``message_type="tool_call"`` rows.
        """
        for msg in messages or []:
            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                name = tc.get("name") or ""
                args = tc.get("arguments") or {}
                if name == "Skill":
                    if isinstance(args, dict) and args.get("skill") == "research":
                        return True
                elif name == "read_document":
                    path = args.get("path") if isinstance(args, dict) else None
                    if isinstance(path, str) and path == self._RESEARCH_SKILL_PATH:
                        return True
            if msg.get("message_type") == "tool_call":
                tool_name = msg.get("tool_name") or ""
                raw = msg.get("tool_arguments") or msg.get("content") or ""
                if tool_name == "Skill" and '"research"' in str(raw):
                    return True
                if tool_name == "read_document" and self._RESEARCH_SKILL_PATH in str(raw):
                    return True
        return False

    def _detect_planner_template(self, messages: List[Dict]) -> str:
        return "legal_research" if self._session_loaded_research_skill(messages) else "default"

    @staticmethod
    def _rehydrate_plan(payload: Dict[str, Any]):
        """Rebuild an ``ExecutionPlan`` from a JSON payload the client echoed
        back on approval. Step statuses and results are reset so execution
        starts from a clean slate (the UI is rendering the fresh plan anyway
        from the re-emitted ``update_plan`` snapshot)."""
        from anylegal_oss.services.planning.planner import ExecutionPlan, PlanStep
        import uuid

        raw_steps = payload.get("steps") or []
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("approved_plan.steps is empty or invalid")

        steps: List[PlanStep] = []
        for idx, raw in enumerate(raw_steps, start=1):
            if not isinstance(raw, dict):
                continue
            desc = (raw.get("description") or "").strip()
            if not desc:
                continue
            steps.append(PlanStep(
                step_number=int(raw.get("step_number") or idx),
                description=desc,
                tool_calls=[],
                status="pending",
                result=None,
                error=None,
            ))
        if not steps:
            raise ValueError("approved_plan has no usable steps")

        return ExecutionPlan(
            plan_id=str(payload.get("plan_id") or uuid.uuid4()),
            goal=str(payload.get("goal") or ""),
            steps=steps,
            reasoning=payload.get("reasoning"),
            status="pending",
        )

    async def _plan_and_execute(
        self,
        *,
        session: "WorkspaceSession",
        user_id: int,
        thread_id: Optional[str],
        user_message: str,
        messages: List[Dict],
        max_turns: int,
        max_budget_usd: Optional[float],
    ) -> AsyncGenerator[AgenticEvent, None]:
        """
        Plan-and-execute loop.

        1. Ask the Planner to decompose ``user_message`` into N steps.
        2. Emit the plan as an update_plan tool call so the UI renders the
           TODO checklist immediately.
        3. For each step, run a bounded reactive loop. Emit an update_plan
           refresh on every status transition.
        4. Final step synthesizes the answer.
        """
        from anylegal_oss.services.planning.planner import get_planner

        planner = get_planner()

        per_step_cap = max(1, max_turns // max(1, self.MAX_ITERATIONS // 8))

        if self._approved_plan is not None:
            try:
                plan = self._rehydrate_plan(self._approved_plan)
                logger.info(
                    f"[PLANNER] approved plan rehydrated: {len(plan.steps)} steps"
                )
            except Exception as e:
                logger.warning(f"[PLANNER] rehydrate failed; re-planning: {e}")
                self._approved_plan = None

        if self._approved_plan is None:

            plan_template = self._detect_planner_template(messages)
            logger.info(f"[PLANNER] selected template: {plan_template}")

            try:
                plan = await planner.create_plan(
                    goal=user_message,
                    context="",
                    available_tools=[t["name"] for t in get_workspace_tools()],
                    model=self.model,
                    plan_template=plan_template,
                )
            except Exception as e:
                logger.warning(f"[PLANNER] create_plan failed; falling back to reactive: {e}")

                async for evt in self._reactive_loop(messages, max_turns, max_budget_usd, thread_id, user_id):
                    yield evt
                return

            async for evt in self._emit_plan_state(plan):
                yield evt
            return

        plan.status = "in_progress"
        async for evt in self._emit_plan_state(plan):
            yield evt

        final_text = ""

        for step in plan.steps:
            if self._cancelled:
                break
            if max_budget_usd and self._total_cost_usd >= max_budget_usd:
                yield AgenticEvent(
                    type="error",
                    data={"error": f"Budget limit ${max_budget_usd} exceeded"},
                )
                plan.mark_step_failed(step.step_number, "budget exceeded")
                async for e in self._emit_plan_state(plan):
                    yield e
                break

            plan.mark_step_in_progress(step.step_number)
            plan.current_step = step.step_number
            async for e in self._emit_plan_state(plan):
                yield e

            is_last = step.step_number == len(plan.steps)
            if is_last:
                nudge_tail = (
                    "This is the FINAL step — produce the user's complete answer by "
                    "synthesizing the findings from prior steps. No more tool calls: "
                    "write the full structured response per the skill's output format, "
                    "with inline citations. When you stop emitting tool calls and reply "
                    "with text, the plan completes."
                )
            else:
                nudge_tail = (
                    "Focus on THIS step only. Use tools as needed (web_search, "
                    "web_search, etc.). When the research for this step is complete, "
                    "stop calling tools and reply with a concise summary of findings "
                    "(2-5 sentences with inline citations). That summary becomes the "
                    "step's result and the plan advances. Do NOT plan ahead or answer "
                    "the user's full question yet — later steps will."
                )
            messages.append({
                "role": "user",
                "content": (
                    f"[Plan step {step.step_number} of {len(plan.steps)}] "
                    f"{step.description}\n\n{nudge_tail}"
                ),
            })

            step_result_text = ""
            try:
                self._last_step_text = ""
                async for evt in self._scoped_reactive_loop(
                    messages=messages,
                    max_turns=per_step_cap,
                    max_budget_usd=max_budget_usd,
                    thread_id=thread_id,
                    user_id=user_id,
                    emit_text_to_stream=is_last,
                ):
                    yield evt
                step_result_text = self._last_step_text
            except Exception as e:
                logger.error(f"[PLANNER] step {step.step_number} raised: {e}", exc_info=True)
                plan.mark_step_failed(step.step_number, str(e))
                async for e2 in self._emit_plan_state(plan):
                    yield e2
                continue

            plan.mark_step_complete(step.step_number, step_result_text)
            async for e in self._emit_plan_state(plan):
                yield e
            final_text = step_result_text or final_text

        plan.status = "completed" if not any(s.status == "failed" for s in plan.steps) else "failed"
        async for e in self._emit_plan_state(plan):
            yield e

        if final_text:
            try:
                await async_db.save_agentic_message(
                    session_id=self._session_id,
                    thread_id=thread_id,
                    user_id=user_id,
                    message_type="assistant",
                    content=final_text,
                    model_used=self.model,
                    tokens_used=self._total_prompt_tokens + self._total_completion_tokens,
                    cost=self._total_cost_usd,
                )
            except Exception as e:
                logger.warning(f"[PLANNER] final assistant persist failed: {e}")

    async def _scoped_reactive_loop(
        self,
        *,
        messages: List[Dict],
        max_turns: int,
        max_budget_usd: Optional[float],
        thread_id: Optional[str],
        user_id: int,
        emit_text_to_stream: bool = True,
    ) -> AsyncGenerator[AgenticEvent, None]:
        """
        One-step mini-loop for planner mode. Yields events; stores the final
        text chunk emitted for the step on ``self._last_step_text`` so the
        caller can persist it on the corresponding PlanStep.

        ``emit_text_to_stream``: when False (non-final plan steps), the step's
        findings are stored on ``self._last_step_text`` but not yielded as a
        text_chunk. Keeps the main answer stream clean — only the final
        synthesis step renders into the chat transcript. Intermediate findings
        are still shown per-step via the PlanChecklist accordion on the client.
        """
        iteration = 0
        self._last_step_text = ""
        while iteration < max_turns:
            iteration += 1
            self._turn_count += 1
            if self._cancelled:
                break
            if max_budget_usd and self._total_cost_usd >= max_budget_usd:
                break

            accumulated_content, tool_calls, usage = await self._call_llm(messages)
            if usage:
                self._total_prompt_tokens += usage.get("prompt_tokens", 0)
                self._total_completion_tokens += usage.get("completion_tokens", 0)
                self._total_cost_usd += usage.get("cost", 0.0)

            if accumulated_content and not tool_calls:
                self._last_step_text = accumulated_content
                if emit_text_to_stream:
                    yield AgenticEvent(
                        type="text_chunk", data={"content": accumulated_content}
                    )
                return

            if tool_calls:
                for tc in tool_calls:
                    tool_call_id = f"call_{iteration}_{tc.get('index', 0)}"
                    yield AgenticEvent(
                        type="tool_call",
                        data={
                            "tool_name": tc["name"], "arguments": tc["arguments"],
                            "tool_call_id": tool_call_id, "streaming": False,
                        },
                    )
                    result = await self._execute_tool(tc)
                    yield AgenticEvent(
                        type="tool_result",
                        data={
                            "tool_name": tc["name"], "tool_call_id": tool_call_id,
                            "success": result.success, "result": result.result,
                            "error": result.error,
                            "execution_time_ms": result.execution_time_ms,
                        },
                    )
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call_id,
                        "content": json.dumps(result.result) if result.success else (result.error or ""),
                    })
                openai_tool_calls = [
                    {
                        "id": tc.get("id") or f"call_{iteration}_{tc.get('index', 0)}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc.get("arguments", {}))
                            if isinstance(tc.get("arguments"), dict)
                            else (tc.get("arguments") or "{}"),
                        },
                    }
                    for tc in tool_calls
                ]
                messages.append({
                    "role": "assistant", "content": accumulated_content or None,
                    "tool_calls": openai_tool_calls,
                })
            else:
                break

    async def _reactive_loop(
        self,
        messages: List[Dict],
        max_turns: int,
        max_budget_usd: Optional[float],
        thread_id: Optional[str],
        user_id: Optional[int],
    ) -> AsyncGenerator[AgenticEvent, None]:
        """Fallback for when the Planner fails — just forward to the normal loop.

        Currently a thin adapter: we re-enter the main loop body below. Used
        only when ``_plan_and_execute`` catches a planner error. For now it
        synthesizes a single text chunk rather than recursing; the main
        agentic loop already handles the reactive case when planner_mode=False.
        """
        yield AgenticEvent(
            type="error",
            data={"error": "Planner unavailable; please retry without planner_mode."},
        )

    async def _auto_compact(
        self,
        messages: List[Dict],
        thread_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        """Perform auto-compaction and return new message list.

        On success, also writes a `compaction_boundary` row to agentic_messages
        so subsequent /chat calls (in fresh processes) replay from the boundary
        rather than the full thread history. Without this DB write, compaction
        would only shrink the in-memory list for the current SSE stream and
        the next request would reload the full unchanged history.
        """
        if not self._session_state:
            logger.warning("No session state for compaction")
            return messages

        try:
            result = await perform_compaction(
                messages=messages,
                session_state=self._session_state,
                custom_instructions=None,
                is_auto=True,
            )

            if result["success"]:

                new_messages = []
                if result["boundary_marker"]:
                    new_messages.append(result["boundary_marker"])
                if result["summary_messages"]:
                    new_messages.extend(result["summary_messages"])
                if result["attachments"]:
                    new_messages.extend(result["attachments"])

                logger.info(f"[AGENTIC] Auto-compaction: {len(messages)} -> {len(new_messages)} messages")

                record_transcript([result["boundary_marker"]], session_id=self._session_id)

                if thread_id:
                    try:

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
                            "is_auto": True,
                        })
                        await async_db.save_agentic_message(
                            session_id=self._session_id,
                            thread_id=thread_id,
                            user_id=user_id or 0,
                            message_type='compaction_boundary',
                            content=summary_str,
                            tool_arguments=boundary_metadata,
                            model_used=self.model,
                        )
                    except Exception as e:
                        logger.warning(f"[AGENTIC] Failed to persist compaction boundary: {e}")

                return new_messages
            else:
                logger.error(f"[AGENTIC] Auto-compaction failed: {result.get('error')}")
                return messages

        except Exception as e:
            logger.error(f"[AGENTIC] Auto-compaction error: {e}")
            return messages

    async def _call_llm(self, messages: List[Dict]) -> tuple:
        """
        Call LLM (non-streaming) with full integration.
        Adapted from original AgenticWorkspaceChat._call_llm()
        """
        from openai import AsyncOpenAI
        from anylegal_oss.core.llm_provider import llm_provider
        from anylegal_oss.workspace.services import get_provider_extra_body

        provider_config = llm_provider.get_provider_config("chat")
        if not provider_config:
            raise ValueError("LLM provider not configured")

        tool_defs = get_workspace_tools()

        current_mode = getattr(self._session_state, "mode", "default") if self._session_state else "default"
        plan_done = bool(getattr(self._session_state, "plan_already_approved", False)) if self._session_state else False
        if current_mode == "plan":
            from anylegal_oss.workspace.tools.workspace_tools import PLAN_MODE_TOOL_NAMES
            tool_defs = [t for t in tool_defs if t["name"] in PLAN_MODE_TOOL_NAMES]
        else:

            blocked = {"exit_plan_mode"}
            if plan_done:
                blocked.add("enter_plan_mode")
            tool_defs = [t for t in tool_defs if t["name"] not in blocked]

        from anylegal_oss.workspace.tools.skill_tool import apply_skill_scope
        tool_defs = apply_skill_scope(tool_defs, self._session_state)

        tools = []
        for tool_def in tool_defs:
            params = tool_def.get("input_schema") or tool_def.get("parameters") or {}
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_def["name"],
                    "description": tool_def.get("description", ""),
                    "parameters": params,
                }
            })

        extra = get_provider_extra_body(self.model) or {}
        reasoning_effort = os.getenv("REASONING_EFFORT", "medium")
        if reasoning_effort != "none":
            extra["reasoning"] = {"effort": reasoning_effort, "exclude": False}

        async with AsyncOpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            default_headers=provider_config.get("default_headers", {}),
            timeout=LLM_HTTP_TIMEOUT,
        ) as client:
            try:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto",
                    max_tokens=64000,
                    extra_body=extra if extra else None,
                )

                content = self._extract_content(response)

                tool_calls = self._extract_tool_calls(response)

                if not tool_calls and content:
                    from.tool_call_rescue import rescue_tool_calls_from_content
                    allowed = [t["name"] for t in get_workspace_tools()]
                    rescued, content = rescue_tool_calls_from_content(content, allowed)
                    if rescued:
                        tool_calls = rescued

                finish_reason = None
                try:
                    choices = response.choices or []
                    if choices:
                        finish_reason = getattr(choices[0], "finish_reason", None)
                except Exception:
                    pass

                usage = response.usage
                if usage:
                    prompt_tokens = usage.prompt_tokens
                    completion_tokens = usage.completion_tokens

                    cost = self._calculate_cost(self.model, prompt_tokens, completion_tokens)
                else:
                    prompt_tokens = completion_tokens = 0
                    cost = 0.0

                logger.info(
                    f"[AGENTIC_ASYNC] non-stream summary: finish_reason={finish_reason} "
                    f"completion_tokens={completion_tokens} content_chars={len(content or '')} "
                    f"tool_calls={len(tool_calls)}"
                )
                if finish_reason == "length":
                    logger.warning(
                        f"[AGENTIC_ASYNC] OUTPUT TRUNCATED (non-stream): "
                        f"completion_tokens={completion_tokens} — provider capped the response."
                    )

                return content, tool_calls, {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost": cost,
                    "finish_reason": finish_reason,
                }

            except Exception as e:
                logger.error(f"LLM call failed: {e}")
                raise

    async def _call_llm_streaming(self, messages: List[Dict]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming variant of ``_call_llm``. Yields deltas as they arrive:

            {"type": "content", "delta": str}         — per content token
            {"type": "done", "content": str,
             "tool_calls": [...], "usage": {...}}      — terminal event with
                                                         full accumulated state

        The outer reactive loop emits ``AgenticEvent(type="text_chunk", …)``
        for each content delta so the frontend renders text as it arrives.
        Tool-call deltas are accumulated internally and flushed on ``done``.

        Tests mock this method directly (see test_enter_exit_plan_mode.py).
        The non-streaming ``_call_llm`` is retained for the planner-service
        path and any code that needs a single awaited tuple.
        """
        from openai import AsyncOpenAI
        from anylegal_oss.core.llm_provider import llm_provider
        from anylegal_oss.workspace.services import get_provider_extra_body

        provider_config = llm_provider.get_provider_config("chat")
        if not provider_config:
            raise ValueError("LLM provider not configured")

        tool_defs = get_workspace_tools()

        current_mode = getattr(self._session_state, "mode", "default") if self._session_state else "default"
        plan_done = bool(getattr(self._session_state, "plan_already_approved", False)) if self._session_state else False
        if current_mode == "plan":
            from anylegal_oss.workspace.tools.workspace_tools import PLAN_MODE_TOOL_NAMES
            tool_defs = [t for t in tool_defs if t["name"] in PLAN_MODE_TOOL_NAMES]
        else:
            blocked = {"exit_plan_mode"}
            if plan_done:
                blocked.add("enter_plan_mode")
            tool_defs = [t for t in tool_defs if t["name"] not in blocked]

        tools = []
        for tool_def in tool_defs:
            params = tool_def.get("input_schema") or tool_def.get("parameters") or {}
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_def["name"],
                    "description": tool_def.get("description", ""),
                    "parameters": params,
                }
            })

        extra = get_provider_extra_body(self.model) or {}
        reasoning_effort = os.getenv("REASONING_EFFORT", "medium")
        if reasoning_effort != "none":
            extra["reasoning"] = {"effort": reasoning_effort, "exclude": False}

        accumulated_content = ""
        accumulated_reasoning = ""
        accumulated_tc: Dict[int, Dict[str, Any]] = {}
        prompt_tokens = 0
        completion_tokens = 0
        finish_reason: Optional[str] = None

        debug_reasoning = os.getenv("DEBUG_REASONING_STREAM", "").lower() in ("1", "true", "yes")
        first_delta_logged = False
        saw_reasoning = False

        # Retry transient upstream drops (e.g. OpenRouter / akashml dropping the
        # SSE mid-turn) only when nothing has been yielded to the caller yet.
        # Once the model has emitted reasoning or content, we surface the error
        # rather than re-issue the request — retrying mid-stream would either
        # double-render or diverge from the partial output the frontend already
        # has.
        from openai import APIConnectionError, APITimeoutError, RateLimitError
        _transient_llm_errors = (APIConnectionError, APITimeoutError, RateLimitError)
        _llm_retry_backoffs = (1.0, 2.0)  # 2 retries on top of the initial attempt

        async with AsyncOpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            default_headers=provider_config.get("default_headers", {}),
            timeout=LLM_HTTP_TIMEOUT,
        ) as client:
          for _attempt_idx in range(len(_llm_retry_backoffs) + 1):
            try:
                stream = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools if tools else None,
                    tool_choice="auto",
                    max_tokens=64000,
                    stream=True,
                    stream_options={"include_usage": True},
                    extra_body=extra if extra else None,
                )

                async for chunk in stream:

                    ch_usage = getattr(chunk, "usage", None)
                    if ch_usage:
                        prompt_tokens = getattr(ch_usage, "prompt_tokens", 0) or 0
                        completion_tokens = getattr(ch_usage, "completion_tokens", 0) or 0

                    choices = getattr(chunk, "choices", None) or []
                    if not choices:
                        continue

                    fr = getattr(choices[0], "finish_reason", None)
                    if fr:
                        finish_reason = fr
                    delta = getattr(choices[0], "delta", None)
                    if not delta:
                        continue

                    if debug_reasoning and not first_delta_logged:
                        first_delta_logged = True
                        try:

                            dumped = delta.model_dump() if hasattr(delta, "model_dump") else (
                                delta.dict() if hasattr(delta, "dict") else vars(delta)
                            )
                            logger.info(f"[AGENTIC_ASYNC] first delta keys={list(dumped.keys())} payload={dumped}")
                        except Exception as e:
                            logger.info(f"[AGENTIC_ASYNC] first delta dump failed: {e}; type={type(delta).__name__}")

                    reasoning_delta = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
                    if reasoning_delta:
                        if debug_reasoning and not saw_reasoning:
                            saw_reasoning = True
                            logger.info(f"[AGENTIC_ASYNC] reasoning tokens DETECTED (first chunk len={len(reasoning_delta)})")
                        accumulated_reasoning += reasoning_delta
                        yield {"type": "reasoning", "delta": reasoning_delta, "accumulated": accumulated_reasoning}

                    content_delta = getattr(delta, "content", None)
                    if content_delta:
                        accumulated_content += content_delta
                        yield {"type": "content", "delta": content_delta}

                    tc_deltas = getattr(delta, "tool_calls", None) or []
                    for tc_delta in tc_deltas:
                        idx = getattr(tc_delta, "index", 0) or 0
                        slot = accumulated_tc.setdefault(idx, {
                            "id": "", "name": "", "arguments": "", "index": idx,
                        })
                        if getattr(tc_delta, "id", None):
                            slot["id"] = tc_delta.id
                        fn = getattr(tc_delta, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                slot["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                slot["arguments"] += fn.arguments

            except _transient_llm_errors as e:
                already_yielded = bool(accumulated_content) or bool(accumulated_reasoning)
                if already_yielded or _attempt_idx >= len(_llm_retry_backoffs):
                    logger.error(
                        f"LLM streaming call failed "
                        f"(attempt {_attempt_idx + 1}, "
                        f"yielded_content={bool(accumulated_content)}, "
                        f"yielded_reasoning={bool(accumulated_reasoning)}): "
                        f"{type(e).__name__}: {e}"
                    )
                    raise
                backoff = _llm_retry_backoffs[_attempt_idx]
                logger.warning(
                    f"LLM streaming transient error on attempt {_attempt_idx + 1} "
                    f"before any output emitted; retrying in {backoff}s: "
                    f"{type(e).__name__}: {e}"
                )
                await asyncio.sleep(backoff)
                first_delta_logged = False
                saw_reasoning = False
                continue
            except Exception as e:
                logger.error(f"LLM streaming call failed: {e}")
                raise
            else:
                break

        tool_calls: List[Dict[str, Any]] = []
        tc_parse_failures = 0
        for idx in sorted(accumulated_tc.keys()):
            slot = accumulated_tc[idx]
            name = (slot["name"] or "").strip()
            raw_args = slot["arguments"] or "{}"
            args = self._parse_tool_arguments(raw_args, name)

            parse_failed = not args and raw_args.strip() not in ("", "{}")
            if parse_failed:
                tc_parse_failures += 1
            if not name:
                continue

            tool_calls.append({
                "id": slot["id"],
                "name": name,
                "arguments": args,
                "index": idx,
                "parse_failed": parse_failed,
                "raw_arguments": raw_args if parse_failed else None,
            })

        rescued_count = 0
        if not tool_calls and accumulated_content:
            from.tool_call_rescue import rescue_tool_calls_from_content
            allowed = [t["name"] for t in get_workspace_tools()]
            rescued, accumulated_content = rescue_tool_calls_from_content(
                accumulated_content, allowed,
            )
            if rescued:
                tool_calls = rescued
                rescued_count = len(rescued)

        cost = self._calculate_cost(self.model, prompt_tokens, completion_tokens) if (prompt_tokens or completion_tokens) else 0.0

        logger.info(
            f"[AGENTIC_ASYNC] stream summary: finish_reason={finish_reason} "
            f"completion_tokens={completion_tokens} content_chars={len(accumulated_content)} "
            f"reasoning_chars={len(accumulated_reasoning)} tool_calls={len(tool_calls)} "
            f"tc_parse_failures={tc_parse_failures} rescued={rescued_count}"
        )

        if finish_reason == "length" or tc_parse_failures > 0:
            truncated_tc_names = [
                (accumulated_tc[i].get("name") or "?")
                for i in sorted(accumulated_tc.keys())
            ]
            logger.warning(
                f"[AGENTIC_ASYNC] OUTPUT TRUNCATED: finish_reason={finish_reason} "
                f"completion_tokens={completion_tokens} tc_parse_failures={tc_parse_failures} "
                f"tool_names={truncated_tc_names}. Provider capped the response — "
                f"the tool call arguments were cut mid-JSON. "
                f"Consider: (a) raising max_tokens if the provider allows, "
                f"(b) switching to a provider without this cap, or "
                f"(c) teaching the skill to split drafts via input_files."
            )

        yield {
            "type": "done",
            "content": accumulated_content,
            "tool_calls": tool_calls,
            "finish_reason": finish_reason,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cost": cost,
            },
        }

    def _extract_content(self, response: Any) -> str:
        """Extract text content from an LLM response (dict or SDK object)."""
        try:
            choices = response.get("choices", []) if isinstance(response, dict) else response.choices
            if not choices:
                return ""
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message", {})
                content = message.get("content", "") or ""
            else:
                message = first.message
                content = getattr(message, "content", "") or ""
            return content
        except Exception as e:
            logger.error(f"Error extracting content: {e}")
            return ""

    def _extract_tool_calls(self, response: Any) -> List[Dict[str, Any]]:
        """Extract tool calls from an LLM response (dict or SDK object)."""
        tool_calls: List[Dict[str, Any]] = []
        try:
            choices = response.get("choices", []) if isinstance(response, dict) else response.choices
            if not choices:
                return []
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message", {})
                raw_calls = message.get("tool_calls") or []
            else:
                message = first.message
                raw_calls = getattr(message, "tool_calls", None) or []

            for call in raw_calls:
                if isinstance(call, dict):
                    call_type = call.get("type")
                    func = call.get("function", {}) or {}
                    call_id = call.get("id", "")
                    call_index = call.get("index", 0)
                else:
                    call_type = getattr(call, "type", "function")
                    func_obj = getattr(call, "function", None)
                    func = {
                        "name": getattr(func_obj, "name", "") if func_obj else "",
                        "arguments": getattr(func_obj, "arguments", "{}") if func_obj else "{}",
                    }
                    call_id = getattr(call, "id", "")
                    call_index = getattr(call, "index", 0)

                if call_type == "function":
                    tool_name = (func.get("name", "") or "").strip()
                    arguments = self._parse_tool_arguments(func.get("arguments", "{}"), tool_name)
                    tool_calls.append({
                        "id": call_id,
                        "name": tool_name,
                        "arguments": arguments,
                        "index": call_index,
                    })
        except Exception as e:
            logger.error(f"Error extracting tool calls: {e}")
        return tool_calls

    def _parse_tool_arguments(self, args_str: str, tool_name: str) -> Dict[str, Any]:
        """Parse tool arguments JSON with basic repair."""
        if not args_str:
            return {}
        try:
            return json.loads(args_str)
        except json.JSONDecodeError:

            if tool_name == "create_document" and '"content"' in args_str:
                try:
                    repaired = args_str.rstrip()
                    if not repaired.endswith('}'):
                        if repaired.endswith('\\'):
                            repaired = repaired[:-1]
                        if not repaired.endswith('"'):
                            repaired += '"'
                        repaired += '}'
                        parsed = json.loads(repaired)
                        if 'path' in parsed and parsed['path']:
                            return parsed
                except:
                    pass

        logger.warning(f"Failed to parse tool arguments for {tool_name}: {args_str[:100]}")
        return {}

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate USD cost for this turn using the model registry.

        Historical bug: this used to import ``get_cost_for_model`` which
        doesn't exist, so every call fell through to a $10/M fallback
        (~5-10× the real OpenRouter price for the models we use). Now uses
        the real ``calculate_action_cost`` and only falls back if the model
        is entirely unknown to the registry.
        """
        try:
            from anylegal_oss.core.pricing import calculate_action_cost
            result = calculate_action_cost(model, prompt_tokens, completion_tokens)

            if isinstance(result, dict):
                return float(result.get("total_cost", 0.0))
            return float(result)
        except Exception as e:
            logger.warning(f"Failed to calculate cost for model {model}: {e}")

            total_tokens = prompt_tokens + completion_tokens
            return (total_tokens / 1_000_000) * 1.00

    async def _execute_tool(self, tool_call: Dict) -> ToolResult:
        """Execute a tool call using AsyncToolExecutor."""
        tool_name = tool_call["name"]
        arguments = tool_call["arguments"]

        try:

            executor = AsyncToolExecutor(
                session=self._workspace,
                user_id=getattr(self._workspace, 'user_id', None),
                model=self.model,
                session_state=self._session_state,
                agent_id=getattr(self, "_agent_id", None),
            )
            result = await executor.execute_async(tool_name, arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result={},
                error=str(e),
                execution_time_ms=0,
            )

    def cancel(self) -> None:
        """Cancel the running agentic loop"""
        self._cancelled = True
        logger.info("[AGENTIC_ASYNC] Cancellation requested")

def create_agentic_chat_async(
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
    session_guard = None,
    planner_mode: bool = False,
    approved_plan: Optional[Dict[str, Any]] = None,
    approved_mode_change: Optional[Dict[str, Any]] = None,
) -> AgenticWorkspaceChatAsync:
    """Create a new async agentic chat instance."""
    return AgenticWorkspaceChatAsync(
        model=model,
        system_prompt=system_prompt,
        session_guard=session_guard,
        planner_mode=planner_mode,
        approved_plan=approved_plan,
        approved_mode_change=approved_mode_change,
    )

