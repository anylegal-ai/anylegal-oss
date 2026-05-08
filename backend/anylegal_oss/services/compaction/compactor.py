"""Basic compactor with PTL (prompt-too-long) retry logic.

Summarization calls go through OpenRouter using the configured chat model.
"""

import asyncio
import json
import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_SUMMARIZE_SYSTEM_PROMPT = (
    "You are summarizing a multi-turn conversation between a user and an AI "
    "assistant for context-window compaction. Produce a concise summary that "
    "preserves: the user's task, key decisions made, code or document edits "
    "applied, and any open questions. Omit small talk and tool-result detail."
)

class BasicCompactor:
    """
    Simple compaction using LLM summarization with PTL retry.
    Mirrors the original system's `compactConversation` but simplified.
    """

    def __init__(self):
        self.max_ptl_retries = 3
        self.ptl_retry_marker = "[earlier conversation truncated for compaction retry]"

    async def compact(
        self,
        messages: List[Dict[str, Any]],
        session_state,
        custom_instructions: Optional[str] = None,
        is_auto: bool = False,
    ) -> Dict[str, Any]:
        """
        Compact conversation by summarizing older messages.

        Args:
            messages: Full conversation history
            session_state: SessionState for tracking metrics
            custom_instructions: Optional guidance for summary
            is_auto: True if triggered by auto-compaction

        Returns:
            Dict with keys:
                - boundary_marker: System message for compact boundary
                - summary_messages: User message with summary
                - attachments: List of file attachments to restore
                - pre_tokens: Estimated tokens before
                - post_tokens: Estimated tokens after
                - success: True if compaction succeeded
                - error: Error message if failed
        """
        if not messages:
            return {"success": False, "error": "No messages to compact"}

        pre_tokens = self._estimate_tokens(messages)
        session_state.compaction_metrics.record_attempt(
            success=False,                          
            is_auto=is_auto,
            ptl_retry=False
        )

        for attempt in range(self.max_ptl_retries):
            try:

                stripped_messages = self._strip_images(messages)

                summary = await self._call_summarize_llm(stripped_messages, custom_instructions)

                if summary.startswith("PROMPT_TOO_LONG"):

                    if attempt < self.max_ptl_retries - 1:
                        logger.warning(f"PTL on compaction attempt {attempt + 1}, truncating and retrying")
                        messages = self._truncate_oldest_groups(messages)
                        continue
                    else:
                        return {"success": False, "error": "Compaction failed: prompt too long after retries"}

                boundary_marker = self._create_boundary_marker(is_auto, pre_tokens, messages[-1].get("uuid"))
                summary_message = self._create_summary_message(summary, is_auto)

                attachments = []

                post_tokens = self._estimate_tokens([boundary_marker, summary_message] + attachments)

                session_state.compaction_metrics.record_attempt(
                    success=True,
                    is_auto=is_auto,
                    ptl_retry=(attempt > 0)
                )

                return {
                    "success": True,
                    "boundary_marker": boundary_marker,
                    "summary_messages": [summary_message],
                    "attachments": attachments,
                    "pre_tokens": pre_tokens,
                    "post_tokens": post_tokens,
                    "summary": summary,
                }

            except Exception as e:
                logger.error(f"Compaction attempt {attempt + 1} failed: {e}")
                if attempt >= self.max_ptl_retries - 1:
                    return {"success": False, "error": f"Compaction failed: {str(e)}"}

        return {"success": False, "error": "Compaction failed after retries"}

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """Rough token estimation (the original system uses tiktoken for cl100k_base)"""

        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += len(content) // 4
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text", "")
                        total += len(text) // 4
        return total

    def _strip_images(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Replace image blocks with [image] placeholder"""
        stripped = []
        for msg in messages:
            if msg.get("role") != "user":
                stripped.append(msg)
                continue

            content = msg.get("content", [])
            if not isinstance(content, list):
                stripped.append(msg)
                continue

            new_content = []
            for block in content:
                if block.get("type") == "image":
                    new_content.append({"type": "text", "text": "[image]"})
                elif block.get("type") == "document":
                    new_content.append({"type": "text", "text": "[document]"})
                else:
                    new_content.append(block)

            new_msg = msg.copy()
            new_msg["content"] = new_content
            stripped.append(new_msg)

        return stripped

    def _truncate_oldest_groups(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Drop oldest API-round groups until context fits.
        Simple heuristic: drop 20% of messages or at least 2.
        """
        if len(messages) <= 2:
            return messages

        drop_count = max(2, len(messages) // 5)
        return messages[drop_count:]

    async def _call_summarize_llm(
        self,
        messages: List[Dict[str, Any]],
        custom_instructions: Optional[str],
    ) -> str:
        """Call OpenRouter to summarize the message list.

        Returns the raw summary string, or a string starting with
        ``PROMPT_TOO_LONG`` so the caller can trigger PTL retry truncation.
        Raises on transport/config errors; caller handles those at the
        ``except Exception`` site in compact().
        """
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY not set; compaction requires an LLM call. "
                "Configure a key or disable auto-compaction."
            )

        model = os.getenv("COMPACTION_MODEL") or os.getenv("DEFAULT_MODEL") or "anthropic/claude-haiku-4.5"

        # Compact body: render the conversation as a single user message so
        # we don't have to map each role to the provider's chat schema.
        rendered = []
        for m in messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, list):
                content = "\n".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            rendered.append(f"[{role}] {content}")

        instructions = (
            custom_instructions.strip()
            if custom_instructions and custom_instructions.strip()
            else "Summarize the conversation."
        )
        user_payload = (
            f"{instructions}\n\n"
            "--- CONVERSATION ---\n"
            + "\n\n".join(rendered)
        )

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SUMMARIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_payload},
            ],
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=15.0, read=120.0, write=15.0, pool=15.0)) as client:
            try:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "HTTP-Referer": "https://anylegal.ai",
                        "X-Title": "AnyLegal OSS",
                    },
                    json=body,
                )
            except httpx.HTTPError as exc:
                raise RuntimeError(f"OpenRouter request failed: {exc}") from exc

        if resp.status_code == 400:
            # OpenRouter surfaces context-window overruns as 400s; mark for
            # the caller's PTL retry path.
            return "PROMPT_TOO_LONG: " + resp.text[:200]
        if resp.status_code != 200:
            raise RuntimeError(
                f"OpenRouter returned {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Unexpected OpenRouter response shape: {json.dumps(data)[:300]}"
            ) from exc

    def _create_boundary_marker(self, is_auto: bool, token_count: int, last_uuid: Optional[str]) -> Dict[str, Any]:
        """Create compact boundary system message"""
        from anylegal_oss.state.transcript import record_transcript
        import uuid

        boundary = {
            "role": "system",
            "content": f"Compaction boundary (auto={is_auto})",
            "type": "system",
            "subtype": "compact_boundary",
            "compact_metadata": {
                "pre_compact_token_count": token_count,
                "auto": is_auto,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        }
        if last_uuid:
            boundary["compact_metadata"]["preserved_segment"] = {
                "anchor_uuid": last_uuid,
                "head_uuid": None,                            
                "tail_uuid": None,
            }
        return boundary

    def _create_summary_message(self, summary: str, is_auto: bool) -> Dict[str, Any]:
        """Create user message containing the summary"""
        import uuid

        marker = "Context compacted for efficiency." if is_auto else "Manual compaction completed."

        return {
            "role": "user",
            "content": [
                {"type": "text", "text": f"{marker}\n\n## Conversation Summary\n\n{summary}"},
            ],
            "type": "user",
            "is_compact_summary": True,
            "is_visible_in_transcript_only": True,
        }

compactor = BasicCompactor()

async def perform_compaction(
    messages: List[Dict[str, Any]],
    session_state,
    custom_instructions: Optional[str] = None,
    is_auto: bool = False,
) -> Dict[str, Any]:
    """
    Perform compaction using the global compactor.
    """
    result = await compactor.compact(messages, session_state, custom_instructions, is_auto)
    return result