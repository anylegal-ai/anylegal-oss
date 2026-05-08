"""
Session restore and switch functionality — mirrors the original system's session management.
Allows switching between sessions (resume) with proper state loading.
"""

import logging
from typing import Optional, List, Dict, Any
from anylegal_oss.state.transcript import load_session_transcript, list_session_transcripts
from anylegal_oss.state.session_state import get_session_state, SessionState

logger = logging.getLogger(__name__)

class SessionManager:
    """
    Manages session lifecycle: list, switch, restore, create.
    """

    def __init__(self):
        self._current_session_id: Optional[str] = None
        self._session_guard = None                              
        logger.info("SessionManager initialized")

    def set_session_guard(self, guard):
        """Inject the async session guard"""
        self._session_guard = guard

    async def switch_session(self, session_id: str, user_id: Optional[int] = None) -> bool:
        """
        Switch to an existing session (resume).
        Loads transcript and state, sets current session.

        Returns True if successful, False if session not found.
        """
        if self._session_guard is None:
            logger.error("Session guard not set on SessionManager")
            return False

        acquired = await self._session_guard.acquire(session_id, timeout=300)
        if not acquired:
            logger.warning(f"Cannot switch to session {session_id}: locked")
            return False

        try:

            messages = load_session_transcript(session_id)
            if not messages:
                logger.warning(f"Session {session_id} has no transcript")
                return False

            state = get_session_state(session_id)

            self._current_session_id = session_id
            logger.info(f"Switched to session {session_id} with {len(messages)} messages")
            return True

        except Exception as e:
            logger.error(f"Failed to switch to session {session_id}: {e}")
            return False
        finally:

            pass

    def get_current_session_id(self) -> Optional[str]:
        """Get the currently active session ID"""
        return self._current_session_id

    def list_available_sessions(self) -> List[Dict[str, Any]]:
        """
        List all session transcripts available for resumption.
        Returns list of session metadata.
        """
        sessions = list_session_transcripts()

        for s in sessions:
            s["is_current"] = (s["session_id"] == self._current_session_id)

        return sessions

    async def create_new_session(self, user_id: int, initial_message: Optional[str] = None) -> str:
        """
        Create a fresh session.
        Returns the new session ID.
        """
        import uuid
        session_id = str(uuid.uuid4())

        state = get_session_state(session_id)

        self._current_session_id = session_id
        logger.info(f"Created new session {session_id} for user {user_id}")

        return session_id

    def release_current_session(self):
        """Clear current session reference (does not release locks)"""
        self._current_session_id = None

session_manager = SessionManager()

def get_session_manager() -> SessionManager:
    """Get the global session manager"""
    return session_manager