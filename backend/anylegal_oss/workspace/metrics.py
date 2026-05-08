"""
Structured metrics emission for the agentic loop.

Emits one JSON line per tool call / validation result. The observer reads
these lines from container stdout to compute aggregate metrics (validation-
failure rate, tool-call count per turn, edit latency).

Why JSON-lines instead of Prometheus: the rest of the Anylegal observer
pipeline already reads container logs; adding a metrics line parser is
cheaper than standing up a separate scrape endpoint.

All emissions are silent — never raise. Observability must not break the
hot path.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("anylegal.metrics")

_TAG = "METRIC_EVT"

def emit_tool_metric(
    tool_name: str,
    outcome: str,                         
    duration_ms: float,
    *,
    session_id: Optional[str] = None,
    pipeline: Optional[str] = None,
    error_class: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit a tool-call outcome event."""
    if pipeline is None:
        pipeline = "production"
    payload: Dict[str, Any] = {
        "kind": "tool_call",
        "tool": tool_name,
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
        "pipeline": pipeline,
        "ts": time.time(),
    }
    if session_id:
        payload["session_id"] = session_id
    if error_class:
        payload["error_class"] = error_class
    if extra:
        payload["extra"] = extra
    _emit(payload)

def emit_validation_metric(
    tool_name: str,
    level: str,                    
    valid: bool,
    errors_count: int,
    warnings_count: int,
    repairs_made: int,
    *,
    session_id: Optional[str] = None,
    pipeline: Optional[str] = None,
) -> None:
    """Emit a DOCX validation outcome event."""
    if pipeline is None:
        pipeline = "production"
    payload: Dict[str, Any] = {
        "kind": "validation",
        "tool": tool_name,
        "level": level,
        "valid": valid,
        "errors_count": errors_count,
        "warnings_count": warnings_count,
        "repairs_made": repairs_made,
        "pipeline": pipeline,
        "ts": time.time(),
    }
    if session_id:
        payload["session_id"] = session_id
    _emit(payload)

def emit_skill_metric(
    skill: str,
    scoping_active: bool,
    declared_tools_count: int,
    *,
    session_id: Optional[str] = None,
    pipeline: Optional[str] = None,
) -> None:
    """Emit a skill invocation event."""
    if pipeline is None:
        pipeline = "production"
    payload = {
        "kind": "skill_invoke",
        "skill": skill,
        "scoping_active": scoping_active,
        "declared_tools_count": declared_tools_count,
        "pipeline": pipeline,
        "ts": time.time(),
    }
    if session_id:
        payload["session_id"] = session_id
    _emit(payload)

def _emit(payload: Dict[str, Any]) -> None:
    try:
        line = json.dumps(payload, separators=(",", ":"), default=str)
        logger.info(f"{_TAG} {line}")
    except Exception as e:  # pragma: no cover

        logger.debug(f"metrics emit failed: {e}")
