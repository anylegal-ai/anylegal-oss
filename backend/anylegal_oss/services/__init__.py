"""
AnyLegal services package — aggregation of all services used by the async agent.
"""

from anylegal_oss.services.compaction import compactor

from anylegal_oss.services.planning.planner import Planner, get_planner

from anylegal_oss.services.skills.skill_matcher import (
    SkillMatcher,
    get_skill_matcher,
    register_skill,
    register_builtin_skills,
)

from anylegal_oss.services.metrics import (
    MetricsCollector,
    metrics,
    get_metrics,
    increment_counter,
    set_gauge,
    record_histogram,
    MetricNames,
    track_request_latency,
)
from anylegal_oss.services.validation import (
    sanitize_string,
    validate_session_id,
    validate_user_id,
    validate_json_body,
    validate_message_content,
    validate_budget_limit,
    validate_max_turns,
    validate_tool_arguments,
    AgenticChatRequest,
    validate_agentic_request,
    ValidationContext,
    validation_context,
)

class _NoAuthRBAC:
    """No-op RBAC for OSS — every check passes."""
    def has_permission(self, user_id, permission):
        return True

def get_rbac_manager():
    return _NoAuthRBAC()

def require_permission(permission):
    """No-op permission decorator for OSS."""
    def decorator(func):
        return func
    return decorator

class Role:
    pass

class Permission:
    pass

class RBACManager:
    pass

__all__ = [

    "compactor",

    "Planner",
    "get_planner",

    "SkillMatcher",
    "get_skill_matcher",
    "register_skill",
    "register_builtin_skills",

    "MetricsCollector",
    "metrics",
    "get_metrics",
    "increment_counter",
    "set_gauge",
    "record_histogram",
    "MetricNames",
    "track_request_latency",
    "sanitize_string",
    "validate_session_id",
    "validate_user_id",
    "validate_json_body",
    "validate_message_content",
    "validate_budget_limit",
    "validate_max_turns",
    "validate_tool_arguments",
    "AgenticChatRequest",
    "validate_agentic_request",
    "ValidationContext",
    "validation_context",
]