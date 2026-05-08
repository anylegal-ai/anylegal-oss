"""
Skill tool — first-class skill invocation, Anthropic/CC parity.

The model calls ``Skill(skill="draft")`` instead of
``read_document("Skills/draft/SKILL.md")``. The tool handler loads the skill
body from the workspace skills directory and returns it as the tool result.
The model reads the body on its next turn and follows the procedure.

Side effects (only when ``SKILL_TOOL_SCOPING=true``):
- Sets ``session_state.active_skill_tools`` to the ``requires.tools`` list
  from the skill frontmatter. The agentic loop reads this at tool-pool build
  (see agentic_chat_async.py) and filters ``WORKSPACE_TOOLS`` to only those
  names plus always-on essentials (``Skill``, ``todo_write``, mode tools).
- Scoping clears automatically on the next user turn — a new user message
  resets ``active_skill_tools`` to ``None`` so the model sees the full pool
  until another skill is invoked.

A copy of the skill body is also recorded on ``session_state.invoked_skills``
so the compactor preserves it across window compaction, matching how the
existing filesystem-walk skill injection behaved.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from ..session import WorkspaceSession

logger = logging.getLogger(__name__)

from .workspace_tools import ALWAYS_ON_TOOLS  # noqa: E402,F401

def skill_invoke(
    skill: str,
    args: Optional[str] = None,
    session: Optional[WorkspaceSession] = None,
    session_state: Optional[Any] = None,
    agent_id: Optional[str] = None,
    **_: Any,
) -> Dict[str, Any]:
    """
    Invoke a skill by name. Returns the full skill body as the tool result.

    Args:
        skill: Skill name (e.g. ``"draft"``, ``"review"``).
        args: Optional slash-command arguments (e.g. ``"-m 'Fix bug'"``).
              Passed through to the skill body as a header line; skills
              can reference it or ignore it.
        session: WorkspaceSession — used to get session_id for record-keeping.
        session_state: SessionState — where ``active_skill_tools`` and
              ``invoked_skills`` get written.
        agent_id: Current agent ID when running as a coordinator worker.

    Returns:
        {"success": bool, "skill": name, "body": str, ...} on success.
        {"success": False, "error": str, "available_skills": [...]} on miss.
    """
    from ..skills.skill_loader import create_skill_loader

    requested_skill = (skill or "").strip()
    if not requested_skill:
        return {
            "success": False,
            "error": "Skill name is required. Pass skill=<name>.",
        }

    skill = requested_skill

    loader = create_skill_loader()
    skill_obj = loader.load_skill(skill, level=3)

    if skill_obj is None:
        available = sorted(s.name for s in loader.discover_skills())
        return {
            "success": False,
            "error": f"Skill '{skill}' not found.",
            "available_skills": available,
        }

    if not loader.is_eligible(skill_obj.metadata):
        return {
            "success": False,
            "error": (
                f"Skill '{skill}' is not eligible in this environment — "
                f"missing required config/binaries."
            ),
        }

    scoping_enabled = os.getenv("SKILL_TOOL_SCOPING", "false").lower() == "true"
    requires_tools = list(skill_obj.metadata.requires.tools or [])

    if scoping_enabled and requires_tools and session_state is not None:

        scoped = sorted(set(requires_tools) | ALWAYS_ON_TOOLS)
        setattr(session_state, "active_skill_tools", scoped)
        logger.info(
            f"[Skill] {skill} scoped tool pool to {len(scoped)} tools "
            f"({len(requires_tools)} declared + {len(ALWAYS_ON_TOOLS)} always-on)"
        )

    if session_state is not None and hasattr(session_state, "record_invoked_skill"):
        try:
            session_state.record_invoked_skill(
                agent_id=agent_id,
                skill_name=requested_skill,
                skill_path=str(skill_obj.path),
                content=skill_obj.content,
            )
        except Exception as e:
            logger.debug(f"[Skill] failed to record invoked skill: {e}")

    body = skill_obj.content
    if args:
        body = f"**Slash-command args:** `{args}`\n\n---\n\n{body}"

    return {
        "success": True,
        "skill": requested_skill,
        "resolved_skill": requested_skill,
        "body": body,
        "declared_tools": requires_tools,
        "scoping_active": scoping_enabled and bool(requires_tools),
    }

def reset_skill_scope(session_state: Any) -> None:
    """
    Clear active_skill_tools. Called by the agent loop at the start of each
    user turn so scoping doesn't bleed across turns.
    """
    if session_state is not None and hasattr(session_state, "active_skill_tools"):
        setattr(session_state, "active_skill_tools", None)

def apply_skill_scope(
    tool_defs: List[Dict[str, Any]],
    session_state: Any,
) -> List[Dict[str, Any]]:
    """
    Filter the tool list to the active skill's declared tools + always-on.

    Returns tool_defs unchanged if no skill is active or scoping is disabled.
    """
    if os.getenv("SKILL_TOOL_SCOPING", "false").lower() != "true":
        return tool_defs

    active = getattr(session_state, "active_skill_tools", None) if session_state else None
    if not active:
        return tool_defs

    allowed = set(active) | ALWAYS_ON_TOOLS
    filtered = [t for t in tool_defs if t.get("name") in allowed]
    logger.debug(
        f"[Skill] tool pool scoped: {len(tool_defs)} -> {len(filtered)} "
        f"(allowed={sorted(allowed)})"
    )
    return filtered

SKILL_TOOLS = {
    "Skill": skill_invoke,
}
