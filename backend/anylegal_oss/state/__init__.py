"""
State management package — simplified the original system bootstrap/state equivalent.
Provides: session_guard, session_state, transcript, session_restore
"""

from anylegal_oss.state.session_guard import (
    AsyncSessionGuard,
    get_session_guard,
    session_guard,
)
from anylegal_oss.state.session_state import (
    SessionState,
    SessionStateManager,
    ModelUsage,
    CompactionMetrics,
    InvokedSkill,
    session_state_manager,
    get_session_state,
)
from anylegal_oss.state.transcript import (
    record_transcript,
    flush_session_storage,
    load_session_transcript,
    list_session_transcripts,
    TranscriptWriter,
    TranscriptLoader,
)
from anylegal_oss.state.session_restore import (
    SessionManager,
    session_manager,
    get_session_manager,
)

__all__ = [

    "AsyncSessionGuard",
    "get_session_guard",
    "session_guard",

    "SessionState",
    "SessionStateManager",
    "ModelUsage",
    "CompactionMetrics",
    "InvokedSkill",
    "session_state_manager",
    "get_session_state",

    "record_transcript",
    "flush_session_storage",
    "load_session_transcript",
    "list_session_transcripts",
    "TranscriptWriter",
    "TranscriptLoader",

    "SessionManager",
    "session_manager",
    "get_session_manager",
]