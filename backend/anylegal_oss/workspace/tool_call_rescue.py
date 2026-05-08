"""
Rescue tool calls that the model emitted as pseudo-XML in content instead of
using the native OpenAI/Anthropic function-calling field.

Some models (notably Kimi K2 on OpenRouter) fall back to emitting tool calls
as Anthropic-style XML inside the assistant's text content:

    <tool>enter_plan_mode</tool>
    <parameter name="reason">Task is multi-dimensional</parameter>

When this happens the provider returns ``tool_calls=[]`` in the
ChatCompletion response and we'd otherwise end the turn with a user-visible
block of raw XML. The rescue parses these patterns and synthesises the tool
calls our dispatch loop expects, so the turn continues.

Guardrails:
- We only rescue when the NATIVE tool_calls list is empty AND the content
  contains at least one ``<tool>`` tag. We never override a model that
  correctly used the native mechanism.
- We strip the parsed XML out of the content so the user doesn't see it
  rendered as prose.
- We only rescue tool names that are in a supplied allowlist — preventing
  accidental dispatch of hallucinated tools.
- The rescue is NOT a substitute for using a capable model. We log every
  rescue at WARNING so they show up in the observer and can be counted.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Sequence, Tuple

logger = logging.getLogger(__name__)

_TOOL_RE = re.compile(
    r"<(?:tool|tool_use|function|function_call)>\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*</(?:tool|tool_use|function|function_call)>",
    re.IGNORECASE,
)
_PARAM_RE = re.compile(
    r'<parameter\s+name\s*=\s*"([^"]+)"\s*>([\s\S]*?)</parameter>',
    re.IGNORECASE,
)

def _xml_unescape(s: str) -> str:
    return (
        s.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )

def rescue_tool_calls_from_content(
    content: str,
    allowed_tool_names: Sequence[str],
) -> Tuple[List[Dict[str, Any]], str]:
    """Parse pseudo-XML tool calls out of ``content``.

    Args:
        content: Assistant content string (may contain 0+ pseudo-tool-calls).
        allowed_tool_names: Names we're willing to dispatch. Rescue ignores
            any tag whose name isn't in this set (logged at DEBUG).

    Returns:
        (tool_calls, stripped_content) — ``tool_calls`` in the same shape the
        dispatcher expects (``{"id", "name", "arguments", "index"}``), and
        the original content with the parsed XML removed.
    """
    if not content or "<" not in content:
        return [], content

    tool_matches = list(_TOOL_RE.finditer(content))
    if not tool_matches:
        return [], content

    tool_calls: List[Dict[str, Any]] = []
    removal_spans: List[Tuple[int, int]] = []

    for i, tm in enumerate(tool_matches):
        name = tm.group(1).strip()
        span_start = tm.start()

        region_end = tool_matches[i + 1].start() if i + 1 < len(tool_matches) else len(content)
        region = content[tm.end():region_end]

        params: Dict[str, Any] = {}
        param_end_in_region = 0
        for pm in _PARAM_RE.finditer(region):
            params[pm.group(1).strip()] = _xml_unescape(pm.group(2))
            param_end_in_region = pm.end()

        removal_spans.append((span_start, tm.end() + param_end_in_region))

        if name not in set(allowed_tool_names):
            logger.warning(
                f"[rescue] hallucinated tool name {name!r} in content "
                f"(not in allowed set) — stripped from output, not dispatched"
            )
            continue

        tool_calls.append({
            "id": f"rescued_{uuid.uuid4().hex[:12]}",
            "name": name,
            "arguments": params,
            "index": len(tool_calls),
        })

    stripped = []
    cursor = 0
    for start, end in sorted(removal_spans):
        stripped.append(content[cursor:start])
        cursor = end
    stripped.append(content[cursor:])
    new_content = re.sub(r"\s{3,}", "\n\n", "".join(stripped)).strip()

    if tool_calls:
        logger.warning(
            f"[rescue] recovered {len(tool_calls)} tool call(s) from pseudo-XML "
            f"content: {[tc['name'] for tc in tool_calls]}"
        )
    return tool_calls, new_content

def try_json_arguments(arguments: Any) -> Any:
    """If an argument value looks like JSON, parse it. Otherwise return as-is.

    Anthropic-style XML puts all values as strings; some models emit
    ``<parameter name="todos">[{...}, {...}]</parameter>`` where the value is
    a JSON-encoded list. Try to unwrap that for each arg.
    """
    if not isinstance(arguments, dict):
        return arguments
    out: Dict[str, Any] = {}
    for k, v in arguments.items():
        if isinstance(v, str):
            s = v.strip()
            if s and s[0] in "[{" and s[-1] in "]}":
                try:
                    out[k] = json.loads(s)
                    continue
                except (json.JSONDecodeError, ValueError):
                    pass
        out[k] = v
    return out
