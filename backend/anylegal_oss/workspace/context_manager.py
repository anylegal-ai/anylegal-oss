"""
Context Window Management for the Agentic Loop.

Mirrors the original system's auto-compact approach:
  - Monitor context usage per iteration
  - When approaching the limit, use the chat model to generate a structured
    summary of the conversation, preserving key details for legal document
    editing (documents, edits, revision IDs, playbook context, citations).
  - Replace old messages with the summary + keep recent turns verbatim.

Three tiers:
  T1: Context monitoring — log token usage, warn at thresholds
  T2: LLM-based auto-compaction — structured summary via chat model
  T3: Error recovery — catch context overflow, compact aggressively, retry
"""

import json
import logging
import os
import time
import urllib.request
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 131_072
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_TTL_SECONDS = 3600                          

_context_cache: Dict[str, int] = {}
_cache_fetched_at: float = 0.0

def _refresh_context_cache() -> None:
    """Fetch context_length for all models from OpenRouter (no auth needed)."""
    global _context_cache, _cache_fetched_at
    try:
        req = urllib.request.Request(_OPENROUTER_MODELS_URL)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        fresh: Dict[str, int] = {}
        for m in data.get("data", []):
            mid = m.get("id")
            ctx = m.get("context_length")
            if mid and ctx:
                fresh[mid] = int(ctx)
        if fresh:
            _context_cache = fresh
            _cache_fetched_at = time.monotonic()
            logger.info(f"[CONTEXT] Cached context windows for {len(fresh)} models from OpenRouter")
    except Exception as e:
        logger.warning(f"[CONTEXT] Failed to fetch model context windows from OpenRouter: {e}")

def _ensure_cache() -> Dict[str, int]:
    """Return the cache, refreshing if stale or empty."""
    if not _context_cache or (time.monotonic() - _cache_fetched_at > _CACHE_TTL_SECONDS):
        _refresh_context_cache()
    return _context_cache

COMPACTION_THRESHOLD = 0.80

AGENTIC_MAX_TOKENS = 64_000

COMPACTION_MAX_TOKENS = 4_000

def estimate_tokens(text: str) -> int:
    """Approximate token count.  ~3.3 chars per token (conservative)."""
    if not text:
        return 0
    return max(1, len(text) // 3)

def get_context_window(model: str) -> int:
    """Get context window size from OpenRouter API cache, fallback to default."""
    cache = _ensure_cache()
    if model in cache:
        return cache[model]
    logger.warning(f"[CONTEXT] Unknown model '{model}', using default {DEFAULT_CONTEXT_WINDOW}")
    return DEFAULT_CONTEXT_WINDOW

def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)

        for tc in msg.get("tool_calls", []):
            func = tc.get("function", {})
            total += estimate_tokens(func.get("arguments", ""))
            total += estimate_tokens(func.get("name", ""))
        total += 4                        
    return total

def effective_input_budget(model: str) -> int:
    """Usable input tokens = context_window - max_tokens."""
    return get_context_window(model) - AGENTIC_MAX_TOKENS

def should_compact(messages: List[Dict[str, Any]], model: str) -> bool:
    """True when estimated tokens exceed the compaction threshold."""
    budget = effective_input_budget(model)
    current = estimate_messages_tokens(messages)
    return current > int(budget * COMPACTION_THRESHOLD)

def context_usage_pct(messages: List[Dict[str, Any]], model: str) -> float:
    """Return context usage as a percentage of effective input budget."""
    budget = effective_input_budget(model)
    if budget <= 0:
        return 100.0
    return (estimate_messages_tokens(messages) / budget) * 100

COMPACTION_SYSTEM_PROMPT = """\
You are summarizing a legal document editing conversation so it can continue \
in a fresh context window.  The conversation history will be replaced with \
your summary, so it must preserve all critical context.

Create a detailed, structured summary with these sections:

1. **Task & Intent** — What the user asked for, success criteria, any constraints.
2. **Documents** — Every document path accessed (read, created, edited), with a \
one-line description of its current state.
3. **Edits Made** — For each edit_document call: path, what was changed (old → new), \
and the revision_ids returned (these are needed for potential revert).
4. **Playbook Context** — Any playbook rules applied, negotiating positions referenced, \
jurisdiction-specific guidance used.
5. **Research & Citations** — Web searches and fetches performed, key findings, \
URLs cited.  Preserve citation text and URLs exactly.
6. **Errors & Fixes** — Failed operations and how they were resolved, or what \
remains unresolved.
7. **All User Messages** — Every user message (not tool results), preserving \
the exact wording.
8. **Pending Tasks** — What remains to be done.
9. **Current State** — Where the work left off and what to do next.

Rules:
- Do NOT reproduce full document content — just note which documents were read \
and their approximate size.  The agent can call read_document again if needed.
- Preserve ALL revision_ids — they are required for revert operations.
- Preserve ALL citation URLs exactly as they appeared.
- Be thorough but concise — this summary replaces the entire conversation.
"""

_SYNTHETIC_USER_MARKERS = (
    "The conversation so far has been summarized",
    "[Earlier conversation was compacted",
)

def _last_real_user_idx(messages: List[Dict[str, Any]]) -> Optional[int]:
    """Index of the most recent non-synthetic user message, or None."""
    for i in range(len(messages) - 1, 0, -1):
        msg = messages[i]
        if msg.get("role") != "user":
            continue
        content = msg.get("content") or ""
        if not isinstance(content, str):
            return i
        if content.startswith(_SYNTHETIC_USER_MARKERS):
            continue
        return i
    return None

async def compact_messages_with_llm(
    messages: List[Dict[str, Any]],
    model: str,
    keep_recent: int = 3,
) -> List[Dict[str, Any]]:
    """Compact messages using an LLM-generated structured summary.

    Mirrors the original system's auto-compact:
      1. Separate system prompt, middle (compactable) messages, and recent turns.
      2. Send middle messages to the LLM with the compaction prompt.
      3. Replace middle messages with the LLM's summary.
      4. Return:  system_prompt + summary + recent_turns

    Falls back to mechanical compaction if the LLM call fails.

    Parameters
    ----------
    messages : list
        Current message array (system + history).
    model : str
        Model name to use for the compaction call.
    keep_recent : int
        Number of recent assistant turns to preserve verbatim.
    """
    if len(messages) <= 4:
        return messages                                 

    system_msg = messages[0]

    keep_from_idx = len(messages)
    assistant_count = 0
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "assistant":
            assistant_count += 1
            if assistant_count >= keep_recent:
                keep_from_idx = i
                break

    last_user_idx = _last_real_user_idx(messages)
    if last_user_idx is not None and last_user_idx < keep_from_idx:
        keep_from_idx = last_user_idx

    if keep_from_idx <= 2:
        return messages                         

    middle = messages[1:keep_from_idx]
    recent = messages[keep_from_idx:]

    conversation_text = _format_messages_for_summary(middle)

    try:
        summary = await _call_llm_for_summary(model, conversation_text)
    except Exception as e:
        logger.warning(f"[CONTEXT] LLM compaction failed ({e}), falling back to mechanical")
        return _mechanical_compact(messages, keep_recent=5)

    compacted = [
        system_msg,
        {
            "role": "user",
            "content": (
                "The conversation so far has been summarized to free context space. "
                "Here is the summary of all prior work:\n\n"
                f"{summary}\n\n"
                "Continue the task based on this summary. If you need to re-read "
                "any document, call read_document again."
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Understood. I have the full context from the summary above — "
                "documents accessed, edits made with revision IDs, playbook rules, "
                "and pending tasks. Continuing where we left off."
            ),
        },
    ] + recent

    old_tokens = estimate_messages_tokens(messages)
    new_tokens = estimate_messages_tokens(compacted)
    logger.info(
        f"[CONTEXT] LLM compaction: {len(messages)} → {len(compacted)} messages, "
        f"~{old_tokens:,} → ~{new_tokens:,} tokens "
        f"({100 - (new_tokens / max(old_tokens, 1)) * 100:.0f}% reduction)"
    )
    return compacted

async def _call_llm_for_summary(model: str, conversation_text: str) -> str:
    """Call the LLM to generate a compaction summary."""
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")

    async with AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=60.0,
    ) as client:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
                {"role": "user", "content": conversation_text},
            ],
            max_tokens=COMPACTION_MAX_TOKENS,
        )
        return response.choices[0].message.content or ""

def _format_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
    """Format a messages array as readable text for the summarization LLM."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        if role == "user":
            parts.append(f"USER: {content}")
        elif role == "assistant":
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                tc_desc = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "?")
                    args = func.get("arguments", "{}")

                    if len(args) > 2000:
                        args = args[:2000] + "... [truncated]"
                    tc_desc.append(f"  - {name}({args})")
                parts.append(f"ASSISTANT (tool calls):\n" + "\n".join(tc_desc))
                if content:
                    parts.append(f"ASSISTANT (thinking): {content[:500]}")
            elif content:
                parts.append(f"ASSISTANT: {content}")
        elif role == "tool":
            tool_id = msg.get("tool_call_id", "?")

            content_str = content if isinstance(content, str) else json.dumps(content)
            if len(content_str) > 3000:
                content_str = content_str[:3000] + "... [truncated for summary]"
            parts.append(f"TOOL RESULT ({tool_id}): {content_str}")

    return "\n\n".join(parts)

def _mechanical_compact(
    messages: List[Dict[str, Any]],
    keep_recent: int = 5,
) -> List[Dict[str, Any]]:
    """Fallback compaction: keep system prompt + last N turns + marker.

    Used when the LLM compaction call fails.
    """
    if len(messages) <= keep_recent + 1:
        return messages

    system_msg = messages[0]

    keep_from = len(messages)
    count = 0
    for i in range(len(messages) - 1, 0, -1):
        if messages[i].get("role") == "assistant":
            count += 1
            if count >= keep_recent:
                keep_from = i
                break

    last_user_idx = _last_real_user_idx(messages)
    if last_user_idx is not None and last_user_idx < keep_from:
        keep_from = last_user_idx

    recent = messages[keep_from:]

    compacted = [
        system_msg,
        {
            "role": "user",
            "content": (
                "[Earlier conversation was compacted to free context space. "
                "If you need document content, call read_document to re-read.]"
            ),
        },
        {
            "role": "assistant",
            "content": "Understood. Continuing with the task.",
        },
    ] + recent

    old_tokens = estimate_messages_tokens(messages)
    new_tokens = estimate_messages_tokens(compacted)
    logger.info(
        f"[CONTEXT] Mechanical compaction: {len(messages)} → {len(compacted)} messages, "
        f"~{old_tokens:,} → ~{new_tokens:,} tokens"
    )
    return compacted

CONTEXT_OVERFLOW_PHRASES = [
    "context_length_exceeded",
    "context length",
    "maximum context",
    "token limit",
    "too many tokens",
    "request too large",
    "context window",
    "prompt is too long",
    "input too long",
    "exceeds the model",
]

def is_context_overflow_error(error: Exception) -> bool:
    """Check if an exception indicates context window overflow."""
    error_str = str(error).lower()
    return any(phrase in error_str for phrase in CONTEXT_OVERFLOW_PHRASES)
