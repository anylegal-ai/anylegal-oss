"""First-boot workspace seeding for OSS single-tenant deployments.

The OSS package strips the multi-tenant signup flow, so a fresh
deployment opens to an empty workspace. To match the polished UX a new
production user gets, we copy the templates from
``anylegal_oss/workspace/seeds/`` into user_id=1's workspace on first
boot.

Idempotent — runs safely on every lifespan startup. Only writes when
the user has no workspace_files yet (i.e. they haven't customized the
templates or replaced them with their own).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _seeds_dir() -> Path:
    """Path to the bundled seed templates."""
    return Path(__file__).parent / "seeds"

def _load_seed(rel_path: str) -> Optional[str]:
    """Read a seed file relative to the seeds dir. Returns None if missing."""
    candidate = _seeds_dir() / rel_path
    if not candidate.is_file():
        logger.debug("Seed file not found: %s", candidate)
        return None
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Could not read seed %s: %s", candidate, e)
        return None

def seed_default_workspace_if_empty(user_id: int = 1) -> bool:
    """Populate user_id's workspace with template files when empty.

    Returns True if seeds were written, False otherwise (workspace
    already had content, or seeds couldn't be read).
    """
    from anylegal_oss.workspace.workspace import Workspace

    ws = Workspace.load(user_id)
    if ws is not None and ws.workspace_files:
        return False                                    

    if ws is None:
        ws = Workspace(user_id=user_id)

    seed_map = {
        "anylegal.md": "anylegal.md",
        "positions.md": "Playbook/positions.md",
        "playbooks/commercial-contracts.md": "Playbook/commercial-contracts.md",
    }

    wrote_any = False
    for src_rel, target_path in seed_map.items():
        content = _load_seed(src_rel)
        if content is None:
            continue
        ws.workspace_files[target_path] = content
        if "/" in target_path:
            folder = target_path.rsplit("/", 1)[0] + "/"
            ws.folders.add(folder)
        wrote_any = True

    if not wrote_any:
        logger.warning(
            "Workspace seeding skipped — no seed files found at %s",
            _seeds_dir(),
        )
        return False

    if ws.save():
        logger.info(
            "Seeded workspace for user_id=%d with %d template file(s)",
            user_id,
            len(seed_map),
        )
        return True

    logger.warning("Workspace seeding failed at save() for user_id=%d", user_id)
    return False
