"""
Session transcript management — mirrors the original system's utils/sessionStorage.js.
Stores conversation history in JSONL format for resumability and debugging.
"""

import os
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from queue import Queue, Empty

logger = logging.getLogger(__name__)

class TranscriptWriter:
    """
    Manages writing session transcripts to disk.
    Uses a queue to batch writes and avoid blocking the main thread.
    Compatible with the original system's transcript format.
    """

    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir or os.getenv("SESSIONS_DIR", "anylegal_sessions"))
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

        self._write_queue: Queue = Queue()
        self._worker_thread: Optional[threading.Thread] = None
        self._shutdown = threading.Event()
        self._batch_size = 10                      
        self._flush_interval = 5.0           

        self._pending_batches: Dict[str, List[str]] = {}
        self._batch_lock = threading.Lock()

        self._start_writer()

    def _start_writer(self):
        """Start background writer thread"""
        if self._worker_thread and self._worker_thread.is_alive():
            return

        self._worker_thread = threading.Thread(
            target=self._writer_loop,
            name="TranscriptWriter",
            daemon=True
        )
        self._worker_thread.start()
        logger.info("Transcript writer thread started")

    def _writer_loop(self):
        """Background loop that drains the write queue"""
        while not self._shutdown.is_set():
            try:
                try:
                    item = self._write_queue.get(timeout=1.0)
                except Empty:
                    self._flush_batch()
                    continue

                if item is None:                         
                    self._write_queue.task_done()
                    break

                try:
                    session_id, line = item
                    with self._batch_lock:
                        batch = self._pending_batches.setdefault(session_id, [])
                        batch.append(line)
                        total = sum(len(b) for b in self._pending_batches.values())
                        if total >= self._batch_size:
                            self._flush_batch_internal()
                finally:
                    self._write_queue.task_done()

            except Exception as e:
                logger.error(f"Error in transcript writer: {e}")

        self._flush_batch()

    def _flush_batch(self):
        """Flush all pending batches (with lock)"""
        with self._batch_lock:
            if self._pending_batches:
                self._flush_batch_internal()

    def _flush_batch_internal(self):
        """Actually write batches to disk, one file per session (must hold lock)"""
        if not self._pending_batches:
            return

        for session_id, lines in list(self._pending_batches.items()):
            if not lines:
                continue
            try:
                file_path = self.sessions_dir / f"{session_id}.jsonl"
                with open(file_path, 'a', encoding='utf-8') as f:
                    for line in lines:
                        f.write(line + '\n')
                logger.debug(f"Wrote {len(lines)} transcript lines to {file_path}")
            except Exception as e:
                logger.error(f"Failed to write transcript batch for {session_id}: {e}")

                continue
            self._pending_batches[session_id] = []

        self._pending_batches = {k: v for k, v in self._pending_batches.items() if v}

    def record(self, message: Dict[str, Any], session_id: Optional[str] = None):
        """Queue a message for transcript recording. session_id is required."""
        if not session_id:
            logger.warning("TranscriptWriter.record: missing session_id, dropping message")
            return

        try:
            if 'timestamp' not in message:
                message['timestamp'] = datetime.now(timezone.utc).isoformat()

            line = json.dumps(message, separators=(',', ':'))
            self._write_queue.put((session_id, line))
        except Exception as e:
            logger.error(f"Failed to serialize transcript message: {e}")

    def flush(self):
        """Force flush any pending writes. Blocks until queued items are processed."""

        try:
            self._write_queue.join()
        except Exception:
            pass
        self._flush_batch()

    def shutdown(self):
        """Stop the writer thread (call on process exit)"""
        self._shutdown.set()
        self._write_queue.put(None)            
        if self._worker_thread:
            self._worker_thread.join(timeout=5.0)

class TranscriptLoader:
    """Load and parse session transcripts"""

    def __init__(self, sessions_dir: Optional[str] = None):
        self.sessions_dir = Path(sessions_dir or os.getenv("SESSIONS_DIR", "anylegal_sessions"))

    def load_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Load all messages for a session from its transcript file.
        Returns list of message dicts.
        """
        file_path = self.sessions_dir / f"{session_id}.jsonl"
        if not file_path.exists():
            logger.warning(f"Transcript not found: {file_path}")
            return []

        messages = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        messages.append(msg)
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in transcript: {e} (line: {line[:100]})")
        except Exception as e:
            logger.error(f"Failed to load transcript {file_path}: {e}")

        logger.info(f"Loaded {len(messages)} messages for session {session_id}")
        return messages

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all available session transcripts with metadata.
        Returns list of {session_id, created_at, message_count, last_modified}.
        """
        sessions = []
        try:
            for file_path in self.sessions_dir.glob("*.jsonl"):
                try:
                    stat = file_path.stat()

                    with open(file_path, 'rb') as f:
                        line_count = sum(1 for _ in f)

                    sessions.append({
                        "session_id": file_path.stem,
                        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                        "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "message_count": line_count,
                        "file_size_bytes": stat.st_size,
                    })
                except Exception as e:
                    logger.warning(f"Error reading session {file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")

        sessions.sort(key=lambda s: s["last_modified"], reverse=True)
        return sessions

    def delete_session(self, session_id: str) -> bool:
        """Delete a session transcript"""
        file_path = self.sessions_dir / f"{session_id}.jsonl"
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted transcript for session {session_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete transcript {session_id}: {e}")
        return False

_transcript_writer: Optional[TranscriptWriter] = None
_transcript_loader: Optional[TranscriptLoader] = None

def get_transcript_writer() -> TranscriptWriter:
    """Get or create global transcript writer"""
    global _transcript_writer
    if _transcript_writer is None:
        _transcript_writer = TranscriptWriter()
    return _transcript_writer

def get_transcript_loader() -> TranscriptLoader:
    """Get or create global transcript loader"""
    global _transcript_loader
    if _transcript_loader is None:
        _transcript_loader = TranscriptLoader()
    return _transcript_loader

def _transcripts_enabled() -> bool:

    return os.getenv("LOG_TRANSCRIPTS", "true").lower() == "true"

def record_transcript(messages: List[Dict[str, Any]], session_id: Optional[str] = None):
    """
    Record one or more messages to the session transcript.
    Thread-safe; can be called from request handlers.

    No-op when LOG_TRANSCRIPTS=false.
    """
    if not _transcripts_enabled():
        return
    writer = get_transcript_writer()
    for msg in messages:
        writer.record(msg, session_id=session_id)

def flush_session_storage():
    """
    Flush transcript writes to disk immediately.
    Used by the original system's eager flush (EAGER_FLUSH).

    No-op when LOG_TRANSCRIPTS=false.
    """
    if not _transcripts_enabled():
        return
    writer = get_transcript_writer()
    writer.flush()

def load_session_transcript(session_id: str) -> List[Dict[str, Any]]:
    """Load a session transcript by ID"""
    loader = get_transcript_loader()
    return loader.load_session(session_id)

def list_session_transcripts() -> List[Dict[str, Any]]:
    """List all session transcripts"""
    loader = get_transcript_loader()
    return loader.list_sessions()

import atexit
atexit.register(lambda: get_transcript_writer().shutdown())