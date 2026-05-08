"""Polling layer — finds workspaces that need recompiling.

Thin wrapper around the db helper so the runner stays free of SQL.
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)

def find_candidates(debounce_seconds: int, limit: int) -> List[str]:
    """Return up to `limit` workspace IDs ready for recompile.

    A workspace is ready when its docs have changed since the last compile
    AND it's been quiet (no edits) for at least `debounce_seconds`. The
    debounce avoids the compiler chasing the user mid-edit.
    """
    from .db import find_workspaces_needing_recompile

    candidates = find_workspaces_needing_recompile(debounce_seconds=debounce_seconds)
    if len(candidates) > limit:
        logger.info(f"Found {len(candidates)} candidates, capping to {limit} per pass")
        candidates = candidates[:limit]
    return candidates
