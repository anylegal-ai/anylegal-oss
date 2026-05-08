"""Async session guard using O_EXCL file locks. One request per session at a time."""

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Allow only the characters we actually generate for session ids: alnum,
# underscore, hyphen, max 128 chars. Anything else is rejected — this
# replaces the previous one-line replace() "sanitizer" that missed
# backslashes, NUL bytes, %2e%2e, and absolute paths.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


def _validate_session_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not _SESSION_ID_RE.fullmatch(session_id):
        raise ValueError(
            f"invalid session_id (must match {_SESSION_ID_RE.pattern})"
        )
    return session_id


class AsyncSessionGuard:
    """Process-safe session guard. Lock files live under SESSION_LOCK_DIR
    (default /tmp/anylegal_sessions) and expire after 300s to recover
    from crashed request handlers."""

    def __init__(self, lock_dir: Optional[str] = None):
        self.lock_dir = Path(
            lock_dir or os.getenv("SESSION_LOCK_DIR", "/tmp/anylegal_sessions")
        )
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 300
        self._held_locks: set[str] = set()

    def _lock_path(self, session_id: str) -> Path:
        return self.lock_dir / f"{_validate_session_id(session_id)}.lock"

    async def acquire(self, session_id: str, timeout: Optional[int] = None) -> bool:
        lock_file = self._lock_path(session_id)
        timeout = timeout or self.timeout
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self._held_locks.add(session_id)
                return True
            except FileExistsError:
                # Lock exists. Check whether it's stale; if so, race-safely
                # remove and retry. We rely on O_EXCL on the next iteration
                # to make sure only one waiter wins after the unlink.
                try:
                    lock_age = time.time() - lock_file.stat().st_mtime
                    if lock_age > self.timeout:
                        logger.warning(
                            f"Removing stale session lock: {session_id} "
                            f"(age: {lock_age:.0f}s)"
                        )
                        try:
                            lock_file.unlink()
                            continue
                        except FileNotFoundError:
                            continue
                        except OSError:
                            pass
                except FileNotFoundError:
                    continue
                except OSError:
                    pass
            except OSError as e:
                logger.error(f"Error acquiring lock for {session_id}: {e}")

            await asyncio.sleep(1)

        return False

    async def release(self, session_id: str) -> None:
        lock_file = self._lock_path(session_id)
        try:
            lock_file.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Error releasing lock for {session_id}: {e}")
        finally:
            self._held_locks.discard(session_id)

    async def is_locked(self, session_id: str) -> bool:
        try:
            return self._lock_path(session_id).exists()
        except (ValueError, OSError):
            return False

    def cleanup_stale_locks(self) -> int:
        """Remove every lock file older than self.timeout. Best-effort; race
        with active acquirers is benign because acquire() re-creates with O_EXCL."""
        removed = 0
        try:
            for lock_file in self.lock_dir.glob("*.lock"):
                try:
                    lock_age = time.time() - lock_file.stat().st_mtime
                except FileNotFoundError:
                    continue
                if lock_age > self.timeout:
                    try:
                        lock_file.unlink()
                        removed += 1
                    except FileNotFoundError:
                        pass
                    except OSError as e:
                        logger.warning(f"could not unlink {lock_file}: {e}")
        except OSError as e:
            logger.error(f"Error during lock cleanup: {e}")
        return removed


session_guard: Optional[AsyncSessionGuard] = None


def get_session_guard() -> AsyncSessionGuard:
    global session_guard
    if session_guard is None:
        session_guard = AsyncSessionGuard()
    return session_guard
