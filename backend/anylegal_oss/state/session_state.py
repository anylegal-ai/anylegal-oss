"""
Session state management — simplified version of the original system's bootstrap/state.ts.
Tracks per-session: cost, model usage, compaction metrics, invoked skills.
"""

import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ModelUsage:
    """Usage statistics for a specific model"""
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0

    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def accumulate(self, usage: "ModelUsage") -> None:
        """Add another usage chunk to this model's totals"""
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cost += usage.cost
        self.cache_read_input_tokens += usage.cache_read_input_tokens
        self.cache_creation_input_tokens += usage.cache_creation_input_tokens

@dataclass
class CompactionMetrics:
    """Compaction statistics for the session"""
    attempts: int = 0
    successes: int = 0
    ptl_retries: int = 0                           
    last_auto_compact_at: Optional[float] = None
    last_manual_compact_at: Optional[float] = None

    @property
    def success_rate(self) -> float:
        if self.attempts == 0:
            return 1.0
        return self.successes / self.attempts

    def record_attempt(self, success: bool, is_auto: bool = False, ptl_retry: bool = False) -> None:
        self.attempts += 1
        if success:
            self.successes += 1
        if ptl_retry:
            self.ptl_retries += 1
        now = time.time()
        if is_auto:
            self.last_auto_compact_at = now
        else:
            self.last_manual_compact_at = now

@dataclass
class InvokedSkill:
    """Record of a skill that was invoked during the session"""
    skill_name: str
    skill_path: str
    content: str                                                                    
    invoked_at: float
    agent_id: Optional[str] = None

@dataclass
class TodoItem:
    """A single TODO entry. Matches the TodoWrite tool tool shape.

    The model sends the entire list on every call; the executor replaces
    whatever was stored. When all items are completed, the list is cleared.
    """
    content: str                                   
    active_form: str                                              
    status: str = "pending"                                     

@dataclass
class SessionState:
    """
    Simplified session state (cost + model usage + compaction metrics).
    Mirrors essential parts of the original system's STATE but Pythonic.
    """
    session_id: str
    total_cost_usd: float = 0.0
    model_usage: Dict[str, ModelUsage] = field(default_factory=dict)
    compaction_metrics: CompactionMetrics = field(default_factory=CompactionMetrics)
    invoked_skills: Dict[str, InvokedSkill] = field(default_factory=dict)                                   

    todos: Dict[str, List[TodoItem]] = field(default_factory=dict)

    mode: str = "default"

    plan_already_approved: bool = False

    start_time: float = field(default_factory=time.time)
    last_interaction_time: float = field(default_factory=time.time)

    turn_count: int = 0

    def update_interaction(self) -> None:
        """Update last interaction timestamp"""
        self.last_interaction_time = time.time()

    def accumulate_cost(self, model: str, usage: ModelUsage) -> None:
        """Accumulate cost and token usage for a model"""
        if model not in self.model_usage:
            self.model_usage[model] = ModelUsage()
        self.model_usage[model].accumulate(usage)
        self.total_cost_usd += usage.cost

    def get_total_input_tokens(self) -> int:
        return sum(m.input_tokens for m in self.model_usage.values())

    def get_total_output_tokens(self) -> int:
        return sum(m.output_tokens for m in self.model_usage.values())

    def increment_turn(self) -> int:
        """Increment turn count and return new value"""
        self.turn_count += 1
        return self.turn_count

    def record_invoked_skill(self, agent_id: Optional[str], skill_name: str, skill_path: str, content: str) -> None:
        """Record that a skill was invoked (for preservation across compaction)"""
        key = f"{agent_id or ''}:{skill_name}"
        self.invoked_skills[key] = InvokedSkill(
            skill_name=skill_name,
            skill_path=skill_path,
            content=content,
            invoked_at=time.time(),
            agent_id=agent_id
        )

    def get_invoked_skills_for_agent(self, agent_id: str) -> Dict[str, InvokedSkill]:
        """Get skills invoked by a specific agent"""
        prefix = f"{agent_id}:"
        return {
            k.split(":", 1)[1]: v
            for k, v in self.invoked_skills.items()
            if k.startswith(prefix)
        }

    def set_todos(self, key: str, items: List[TodoItem]) -> List[TodoItem]:
        """Replace the todo list for ``key`` (session_id or agent_id).

        If every item is completed, the stored list is cleared — matches
        the TodoWrite tool behavior of keeping context clean once work is done.
        Returns the resulting stored list (empty if cleared).
        """
        all_done = bool(items) and all(t.status == "completed" for t in items)
        stored = [] if all_done else list(items)
        self.todos[key] = stored
        return stored

    def get_todos(self, key: str) -> List[TodoItem]:
        """Return the todos for a given key (session_id or agent_id)."""
        return self.todos.get(key, [])

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "session_id": self.session_id,
            "total_cost_usd": self.total_cost_usd,
            "model_usage": {
                model: asdict(usage)
                for model, usage in self.model_usage.items()
            },
            "compaction_metrics": asdict(self.compaction_metrics),
            "invoked_skills": {
                key: asdict(skill)
                for key, skill in self.invoked_skills.items()
            },
            "todos": {
                key: [asdict(t) for t in items]
                for key, items in self.todos.items()
            },
            "mode": self.mode,
            "plan_already_approved": self.plan_already_approved,
            "start_time": self.start_time,
            "last_interaction_time": self.last_interaction_time,
            "turn_count": self.turn_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        """Deserialize from dict"""
        state = cls(
            session_id=data["session_id"],
            total_cost_usd=data.get("total_cost_usd", 0.0),
            start_time=data.get("start_time", time.time()),
            last_interaction_time=data.get("last_interaction_time", time.time()),
            turn_count=data.get("turn_count", 0),
        )

        for model, usage_data in data.get("model_usage", {}).items():
            state.model_usage[model] = ModelUsage(**usage_data)

        if "compaction_metrics" in data:
            state.compaction_metrics = CompactionMetrics(**data["compaction_metrics"])

        for key, skill_data in data.get("invoked_skills", {}).items():
            state.invoked_skills[key] = InvokedSkill(**skill_data)

        for key, raw_list in data.get("todos", {}).items():
            if isinstance(raw_list, list):
                state.todos[key] = [
                    TodoItem(**t) if isinstance(t, dict) else t for t in raw_list
                ]

        state.mode = data.get("mode", "default") or "default"
        state.plan_already_approved = bool(data.get("plan_already_approved", False))

        return state

class SessionStateManager:
    """
    Manages SessionState lifecycle.
    Stores state in memory with optional persistence to workspace DB.
    """

    def __init__(self):
        self._states: Dict[str, SessionState] = {}
        logger.info("SessionStateManager initialized")

    def get_or_create(self, session_id: str) -> SessionState:
        """Get existing state from memory, else restore from DB, else create new."""
        if session_id in self._states:
            return self._states[session_id]
        restored = self.restore(session_id)
        if restored is not None:
            return restored
        self._states[session_id] = SessionState(session_id=session_id)
        logger.info(f"Created new SessionState for {session_id}")
        return self._states[session_id]

    def get(self, session_id: str) -> Optional[SessionState]:
        """Get state if exists"""
        return self._states.get(session_id)

    def remove(self, session_id: str) -> None:
        """Remove state from memory (does not delete persistent storage)"""
        if session_id in self._states:
            del self._states[session_id]

    def persist(self, session_id: str) -> bool:
        """
        Persist session state to the ``session_states`` table.

        The table is created on first access (idempotent). Returns True on
        success. Never raises — persistence failures are logged and swallowed
        so they can't interrupt the agentic loop.
        """
        state = self._states.get(session_id)
        if not state:
            logger.warning(f"Cannot persist: no state for {session_id}")
            return False

        try:
            import json
            from anylegal_oss.db.database import get_db_connection

            state_json = json.dumps(state.to_dict(), separators=(",", ":"))
            now = time.time()

            with get_db_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS session_states (
                        session_id TEXT PRIMARY KEY,
                        state_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO session_states (session_id, state_json, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(session_id) DO UPDATE SET
                        state_json = excluded.state_json,
                        updated_at = excluded.updated_at
                    """,
                    (session_id, state_json, now),
                )
                conn.commit()
            logger.debug(
                f"Persisted state for {session_id}: "
                f"cost=${state.total_cost_usd:.4f}, turns={state.turn_count}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to persist state for {session_id}: {e}")
            return False

    def restore(self, session_id: str) -> Optional[SessionState]:
        """
        Load state from the ``session_states`` table if present. Inserts
        the restored state into the in-memory map on success.
        """
        try:
            import json
            from anylegal_oss.db.database import get_db_connection

            with get_db_connection() as conn:
                row = conn.execute(
                    "SELECT state_json FROM session_states WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
            if not row:
                return None
            data = json.loads(row["state_json"] if hasattr(row, "keys") else row[0])
            state = SessionState.from_dict(data)
            self._states[session_id] = state
            logger.info(f"Restored state for {session_id} (turns={state.turn_count})")
            return state
        except Exception as e:

            if "no such table" in str(e).lower():
                return None
            logger.error(f"Failed to restore state for {session_id}: {e}")
            return None

    def cleanup_old_sessions(self, max_age_seconds: float = 3600) -> int:
        """
        Remove old sessions from memory.
        Returns count of sessions removed.
        """
        cutoff = time.time() - max_age_seconds
        removed = 0
        for sid in list(self._states.keys()):
            state = self._states[sid]
            if state.last_interaction_time < cutoff:

                self.persist(sid)
                del self._states[sid]
                removed += 1
        return removed

session_state_manager = SessionStateManager()

def get_session_state(session_id: str) -> SessionState:
    """Convenience accessor"""
    return session_state_manager.get_or_create(session_id)