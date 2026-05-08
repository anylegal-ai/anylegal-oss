"""
Input validation and sanitization utilities.
Phase 4: Permissions + Polish
"""

import re
import logging
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, ValidationError, Field, validator
from fastapi import HTTPException, status
from fastapi import Request

logger = logging.getLogger(__name__)

class ValidationError(Exception):
    """Custom validation error"""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

def sanitize_string(value: str, max_length: int = 1000, allow_newlines: bool = False) -> str:
    """
    Sanitize a string input.

    Args:
        value: Raw string
        max_length: Maximum allowed length
        allow_newlines: Whether to allow newline characters

    Returns:
        Sanitized string

    Raises:
        ValidationError if invalid
    """
    if not isinstance(value, str):
        raise ValidationError("value", "Must be a string")

    value = value.strip()

    if len(value) > max_length:
        raise ValidationError("value", f"Length exceeds maximum {max_length}")

    if not allow_newlines:

        value = value.replace('\n', ' ').replace('\r', ' ')

    value = ''.join(ch for ch in value if ch >= ' ' or ch == '\t')

    return value

def validate_session_id(session_id: str) -> str:
    """Validate session ID format (UUID)"""
    if not session_id:
        raise ValidationError("session_id", "Session ID required")

    session_id = str(session_id).strip()

    uuid_pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$'
    simple_pattern = r'^[a-zA-Z0-9_-]+$'

    if not (re.match(uuid_pattern, session_id) or re.match(simple_pattern, session_id)):
        raise ValidationError("session_id", "Invalid session ID format")

    if len(session_id) > 100:
        raise ValidationError("session_id", "Session ID too long")

    return session_id

def validate_user_id(user_id: Any) -> int:
    """Validate user ID"""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        raise ValidationError("user_id", "Must be an integer")

    if user_id < 0:
        raise ValidationError("user_id", "Must be non-negative")

    if user_id > 2**31 - 1:                         
        raise ValidationError("user_id", "User ID too large")

    return user_id

def validate_json_body(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """
    Validate JSON request body.

    Args:
        data: Parsed JSON body
        required_fields: List of required field names

    Returns:
        Validated data (may be modified)

    Raises:
        HTTPException if validation fails
    """
    missing = [f for f in required_fields if f not in data]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required fields: {', '.join(missing)}"
        )

    for key, value in data.items():
        if isinstance(value, str):
            try:
                data[key] = sanitize_string(value, max_length=5000)
            except ValidationError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {key}: {e.message}"
                )

    return data

def validate_message_content(content: Any, max_length: int = 10000) -> str:
    """
    Validate user message content.

    Args:
        content: Message content (string or list)
        max_length: Maximum allowed length

    Returns:
        Validated content as string
    """
    if isinstance(content, list):

        text_parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get('type') == 'text':
                    text_parts.append(block.get('text', ''))
        content = ' '.join(text_parts)

    if not isinstance(content, str):
        raise ValidationError("message", "Message must be string or content blocks")

    return sanitize_string(content, max_length=max_length, allow_newlines=True)

def validate_budget_limit(budget: Any) -> Optional[float]:
    """Validate budget limit"""
    if budget is None:
        return None

    try:
        budget = float(budget)
    except (TypeError, ValueError):
        raise ValidationError("max_budget_usd", "Must be a number")

    if budget < 0:
        raise ValidationError("max_budget_usd", "Budget cannot be negative")

    if budget > 10000:
        raise ValidationError("max_budget_usd", "Budget exceeds maximum (10000)")

    return budget

def validate_max_turns(turns: Any) -> int:
    """Validate max_turns parameter"""
    try:
        turns = int(turns)
    except (TypeError, ValueError):
        raise ValidationError("max_turns", "Must be an integer")

    if turns < 1:
        raise ValidationError("max_turns", "Must be at least 1")

    if turns > 500:
        raise ValidationError("max_turns", "Maximum 500 turns")

    return turns

def validate_tool_arguments(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate tool arguments.

    Args:
        tool_name: Name of the tool
        arguments: Tool arguments dict

    Returns:
        Validated arguments
    """

    sanitized = {}

    for key, value in arguments.items():
        if isinstance(value, str):

            if tool_name in ('write_document', 'create_document'):
                sanitized[key] = sanitize_string(value, max_length=100000, allow_newlines=True)
            elif tool_name == 'search_web':
                sanitized[key] = sanitize_string(value, max_length=500)
            else:
                sanitized[key] = sanitize_string(value, max_length=5000)
        else:
            sanitized[key] = value

    return sanitized

class AgenticChatRequest(BaseModel):
    """Validated agentic chat request.

    ``user_id`` is intentionally optional here — the authoritative user is
    resolved from the JWT by the FastAPI dependency, not from the body.
    Extra fields from the v1 payload shape (``documents``, ``history``,
    ``context``, ``attached_files``, ...) are ignored so the frontend can
    call v2 with its existing request body.
    """
    model_config = {"extra": "ignore"}

    session_id: str = Field(..., min_length=1, max_length=100)
    user_id: Optional[int] = Field(None, ge=0, le=2**31-1)
    message: str = Field(..., min_length=1, max_length=10000)
    thread_id: Optional[str] = Field(None, max_length=100)
    max_turns: int = Field(50, ge=1, le=500)
    max_budget_usd: Optional[float] = Field(None, ge=0, le=10000)
    model: Optional[str] = Field(None, max_length=100)

    planner_mode: bool = False

    deep_research_toggle: bool = False

    approved_plan: Optional[Dict[str, Any]] = None

    approved_mode_change: Optional[Dict[str, Any]] = None

    active_document: Optional[str] = Field(None, max_length=500)

    @validator('session_id')
    def validate_session_id(cls, v):
        return validate_session_id(v)

    @validator('message')
    def validate_message(cls, v):
        return sanitize_string(v, max_length=10000, allow_newlines=True)

async def validate_agentic_request(request: Request) -> AgenticChatRequest:
    """
    Validate agentic chat request.
    Use as: request = Depends(validate_agentic_request)
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body"
        )

    try:
        return AgenticChatRequest(**body)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.errors()
        )

class ValidationContext:
    """
    Holds validation configuration and overrides.
    Can be used to relax/restrict validation based on user role.
    """

    def __init__(self):
        self.max_message_length = 10000
        self.max_session_id_length = 100
        self.strict_mode = False                                      

validation_context = ValidationContext()

def get_validation_context() -> ValidationContext:
    """Get the global validation context"""
    return validation_context