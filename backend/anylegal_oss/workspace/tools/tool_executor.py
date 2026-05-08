"""
Tool Executor

Central dispatcher for executing workspace tools.
Handles tool routing, argument validation, error handling, and result formatting.
"""

import logging
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable, List

from ..session import WorkspaceSession
from .document_tools import DOCUMENT_TOOLS
from .web_tools import WEB_TOOLS
from .legal_tools import LEGAL_TOOLS
from .docx_tools import DOCX_TOOLS
from .python_tools import PYTHON_TOOLS
from .todo_tool import TODO_TOOLS
from .mode_tools import MODE_TOOLS
from .skill_tool import SKILL_TOOLS
from .comment_tools import COMMENT_TOOLS
from .wiki_tools import WIKI_TOOLS

logger = logging.getLogger(__name__)

@dataclass
class ToolResult:
    """Result of a tool execution."""
    success: bool
    tool_name: str
    result: Dict[str, Any]
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "result": self.result,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "timestamp": self.timestamp
        }

class ToolExecutor:
    """
    Executes tools on behalf of the agentic loop.

    Manages tool dispatch, session context injection, and change tracking.
    """

    def __init__(
        self,
        session: WorkspaceSession,
        user_id: Optional[int] = None,
        model: Optional[str] = None,
        session_state: Optional[Any] = None,
        agent_id: Optional[str] = None,
    ):
        """
        Initialize the tool executor.

        Args:
            session: Workspace session for document operations
            user_id: User ID for billing and user-specific data
            model: Model override for LLM-based tools
            session_state: SessionState for tools that need per-session storage
                (notably todo_write, which keys todos by agent_id or session_id).
            agent_id: Current agent ID when running as a coordinator worker.
                Used as the todo_write storage key so workers don't pollute
                the parent session's todo list.
        """
        self.session = session
        self.user_id = user_id
        self.model = model
        self.session_state = session_state
        self.agent_id = agent_id

        self._handlers: Dict[str, Callable] = {}
        self._handlers.update(DOCUMENT_TOOLS)
        self._handlers.update(WEB_TOOLS)
        self._handlers.update(LEGAL_TOOLS)
        self._handlers.update(DOCX_TOOLS)
        self._handlers.update(PYTHON_TOOLS)
        self._handlers.update(TODO_TOOLS)
        self._handlers.update(MODE_TOOLS)
        self._handlers.update(SKILL_TOOLS)
        self._handlers.update(COMMENT_TOOLS)
        self._handlers.update(WIKI_TOOLS)

        self.tool_calls: List[Dict[str, Any]] = []

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        Execute a tool by name with given arguments.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with execution result or error
        """
        start_time = datetime.now(timezone.utc)

        tool_name = (tool_name or "").strip()

        handler = self._handlers.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result={},
                error=f"Unknown tool: {tool_name}. Available tools: {list(self._handlers.keys())}"
            )

        try:

            enriched_args = self._enrich_arguments(tool_name, arguments)

            result = handler(**enriched_args)

            self._inject_post_execution_hints(tool_name, result)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            try:
                from ..metrics import emit_tool_metric, emit_validation_metric
                sid = self.session.session_id if self.session else None
                emit_tool_metric(
                    tool_name=tool_name,
                    outcome="success" if result.get("success", True) else "failure",
                    duration_ms=execution_time,
                    session_id=sid,
                )

                if isinstance(result.get("validation"), dict):
                    v = result["validation"]
                    emit_validation_metric(
                        tool_name=tool_name,
                        level=v.get("level", "light"),
                        valid=bool(v.get("valid", True)),
                        errors_count=len(v.get("errors", [])),
                        warnings_count=len(v.get("warnings", [])),
                        repairs_made=int(v.get("repairs_made", 0) or 0),
                        session_id=sid,
                    )
            except Exception:
                pass                                         

            self.tool_calls.append({
                "tool_name": tool_name,
                "arguments": arguments,
                "success": result.get("success", True),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            return ToolResult(
                success=result.get("success", True),
                tool_name=tool_name,
                result=result,
                error=result.get("error"),
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {e}")
            logger.debug(traceback.format_exc())

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return ToolResult(
                success=False,
                tool_name=tool_name,
                result={},
                error=f"Execution error: {str(e)}",
                execution_time_ms=execution_time
            )

    def _enrich_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Enrich tool arguments with context from session.

        Different tools need different context injected.
        """
        enriched = arguments.copy()

        if tool_name in DOCUMENT_TOOLS:
            enriched["session"] = self.session

        if tool_name in LEGAL_TOOLS:
            enriched["session"] = self.session
            enriched["user_id"] = self.user_id
            enriched["model"] = self.model

        if tool_name in DOCX_TOOLS:
            enriched["session"] = self.session

        if tool_name in PYTHON_TOOLS:
            enriched["session"] = self.session

        if tool_name in TODO_TOOLS:
            enriched["session_state"] = self.session_state
            enriched["todo_key"] = self.agent_id or (self.session.session_id if self.session else "")

        if tool_name in SKILL_TOOLS:
            enriched["session"] = self.session
            enriched["session_state"] = self.session_state
            enriched["agent_id"] = self.agent_id

        if tool_name in COMMENT_TOOLS:
            enriched["session"] = self.session

        if tool_name in WIKI_TOOLS:
            enriched["session"] = self.session

        return enriched

    def _inject_post_execution_hints(
        self, tool_name: str, result: Dict[str, Any]
    ) -> None:
        """Append context hints to a successful tool result (in-place).

        Currently only nudges on run_code(language=node) when it produced
        a DOCX and the session's todo list has pending items. Other tools
        get no hint. Idempotent; safe to call on every tool result.
        """
        if tool_name != "run_code" or not result.get("success"):
            return
        if not self.session_state:
            return

        files = result.get("files_created") or []
        if not any(
            isinstance(f, dict) and f.get("type") == "docx"
            and f.get("added_to_workspace")
            for f in files
        ):
            return
        todo_key = self.agent_id or (
            self.session.session_id if self.session else ""
        )
        try:
            todos = self.session_state.get_todos(todo_key) or []
        except Exception:
            return
        if not todos:
            return
        pending = [t for t in todos if (t.get("status") or "").lower() != "completed"]
        if not pending:
            return

        completed = len(todos) - len(pending)
        sample = [
            t.get("content") or t.get("activeForm") or "(unnamed)"
            for t in pending[:3]
        ]
        result["todo_reminder"] = (
            f"{completed}/{len(todos)} todo items complete. Remaining: "
            + "; ".join(sample)
            + (". Do NOT end your turn until every item is complete — "
               "continue with the next run_code now.")
        )

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self._handlers.keys())

    def get_tool_call_history(self) -> List[Dict[str, Any]]:
        """Get history of tool calls for this executor."""
        return self.tool_calls.copy()

class AsyncToolExecutor(ToolExecutor):
    """
    Async version of ToolExecutor for use with async agentic loop.

    Uses async versions of web tools.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        from .web_tools import WEB_TOOLS_ASYNC
        self._async_handlers = {**self._handlers}
        self._async_handlers.update(WEB_TOOLS_ASYNC)

    async def execute_async(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """
        Execute a tool asynchronously.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            ToolResult with execution result or error
        """
        start_time = datetime.now(timezone.utc)

        tool_name = (tool_name or "").strip()

        handler = self._async_handlers.get(tool_name)
        if not handler:
            return ToolResult(
                success=False,
                tool_name=tool_name,
                result={},
                error=f"Unknown tool: {tool_name}"
            )

        try:

            enriched_args = self._enrich_arguments(tool_name, arguments)

            import asyncio
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**enriched_args)
            else:

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: handler(**enriched_args)
                )

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            try:
                from ..metrics import emit_tool_metric, emit_validation_metric
                sid = self.session.session_id if self.session else None
                emit_tool_metric(
                    tool_name=tool_name,
                    outcome="success" if result.get("success", True) else "failure",
                    duration_ms=execution_time,
                    session_id=sid,
                )
                if isinstance(result.get("validation"), dict):
                    v = result["validation"]
                    emit_validation_metric(
                        tool_name=tool_name,
                        level=v.get("level", "light"),
                        valid=bool(v.get("valid", True)),
                        errors_count=len(v.get("errors", [])),
                        warnings_count=len(v.get("warnings", [])),
                        repairs_made=int(v.get("repairs_made", 0) or 0),
                        session_id=sid,
                    )
            except Exception:
                pass

            self.tool_calls.append({
                "tool_name": tool_name,
                "arguments": arguments,
                "success": result.get("success", True),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            return ToolResult(
                success=result.get("success", True),
                tool_name=tool_name,
                result=result,
                error=result.get("error"),
                execution_time_ms=execution_time
            )

        except Exception as e:
            logger.error(f"Async tool execution error for {tool_name}: {e}")
            logger.debug(traceback.format_exc())

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

            return ToolResult(
                success=False,
                tool_name=tool_name,
                result={},
                error=f"Execution error: {str(e)}",
                execution_time_ms=execution_time
            )
