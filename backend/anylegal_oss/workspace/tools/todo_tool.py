"""
TodoWrite tool — agent-managed in-conversation task list.

The model sends the *entire* updated list on every call. When every item
is ``completed``, the stored list is cleared (keeps context lean). Todos
are stored per-agent: keyed by ``agent_id`` for coordinator workers so
their progress doesn't overwrite the parent session's list; keyed by
``session_id`` otherwise. Auto-approved — never blocks the flow.

This is a **general-purpose progress tool**: available in every mode
(reactive, plan, coordinator). The TodoList UI in the frontend renders
the stored list whether it came from a planner-service emission or from
the model calling this tool directly.
"""

from typing import Any, Dict, List

from anylegal_oss.state.session_state import TodoItem

TODO_WRITE_TOOL = {
    "name": "todo_write",
    "description": (
        "Update the session todo list. Use proactively to track progress on "
        "complex tasks (3+ steps). Send the ENTIRE updated list on every "
        "call — not deltas. Exactly ONE task must be 'in_progress' at a "
        "time. Mark 'completed' immediately after finishing, don't batch."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "todos": {
                "type": "array",
                "description": "The full todo list (replace semantics).",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Imperative form, e.g. 'Read the NDA'",
                        },
                        "active_form": {
                            "type": "string",
                            "description": "Present continuous, e.g. 'Reading the NDA'",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                        },
                    },
                    "required": ["content", "active_form", "status"],
                },
            }
        },
        "required": ["todos"],
    },
}

def todo_write(
    todos: List[Dict[str, Any]],
    session_state=None,
    todo_key: str = "",
    **_: Any,
) -> Dict[str, Any]:
    """Replace the stored todo list for ``todo_key``.

    Returns a CC-style reminder message plus the before/after lists so the
    caller can project the new list into SSE events and session storage.
    """
    if session_state is None:
        return {
            "success": False,
            "error": "todo_write called without session_state context",
            "todos": [],
        }

    items: List[TodoItem] = []
    for raw in todos or []:
        if not isinstance(raw, dict):
            continue
        content = (raw.get("content") or "").strip()
        active_form = (raw.get("active_form") or "").strip()
        status = raw.get("status") or "pending"
        if not content:
            continue
        if status not in ("pending", "in_progress", "completed"):
            status = "pending"
        items.append(TodoItem(
            content=content,
            active_form=active_form or content,
            status=status,
        ))

    in_progress_count = sum(1 for t in items if t.status == "in_progress")
    warning = None
    if in_progress_count > 1:
        warning = (
            f"{in_progress_count} tasks marked in_progress; exactly one "
            "should be in_progress at a time. Proceed, but split work into "
            "sequential steps next call."
        )

    previous = session_state.get_todos(todo_key)
    stored = session_state.set_todos(todo_key, items)

    return {
        "success": True,
        "todos": [
            {"content": t.content, "active_form": t.active_form, "status": t.status}
            for t in stored
        ],
        "previous_todos": [
            {"content": t.content, "active_form": t.active_form, "status": t.status}
            for t in previous
        ],
        "cleared": len(items) > 0 and len(stored) == 0,
        "warning": warning,
        "message": (
            "Todos have been modified successfully. Ensure that you "
            "continue to use the todo list to track your progress. Please "
            "proceed with the current tasks if applicable."
        ),
    }

TODO_TOOLS = {
    "todo_write": todo_write,
}

TODO_WRITE_GUIDANCE = """\
You have access to a todo_write tool. Use it proactively to track progress on complex tasks.

When to use (MANDATORY):
- Any legal research question you estimate will require 3+ tool calls — your FIRST action must be a todo_write enumerating the dimensions you plan to explore (statute / case law / regulatory / market / synthesis).
- Any multi-deliverable task — drafting a SET / SERIES / PACKAGE of documents, producing N memos, reviewing N clauses one-by-one. Before you create the first deliverable, call todo_write with ONE item per deliverable. The list IS the plan.
- Tasks that decompose into 3+ distinct steps AND where the user has given you a concrete task to perform.
- User explicitly asks for a todo list or asks you to "track", "plan", "break down" the work.

When NOT to use:
- Single trivial tasks.
- Purely conversational or quick answers.
- Fewer than 3 meaningful steps.
- Slash-command-only messages (e.g. "/research" alone just loads a skill — no task yet to decompose).
- Before the user has provided an actual question or task.

Hard rules — no exceptions:

1. Send the ENTIRE updated list on every todo_write call (replace semantics, not delta).
2. Every item must have content (imperative, e.g. "Run tests") and active_form (present continuous, e.g. "Running tests").
3. Exactly ONE task is "in_progress" at any time.
4. **Update before continuing work.** Whenever tool results have just been returned to you for the current in_progress item, your VERY NEXT tool call MUST be todo_write to mark that item "completed" and set the next item "in_progress". You may NOT call web_search, web_fetch, run_code, create_document, read_document, or any other tool until todo_write has been called. There is no exception for "I'll batch the update at the end" or "the next step is obvious" — call todo_write first, then call the next research tool. The frontend renders this list as the user's progress bar; skipping the update makes the task look stalled.
5. Mark items "completed" the same iteration they finish — never batch updates across iterations.
6. If blocked, keep the current item "in_progress" and add a new item describing what needs to resolve first.
7. **Never pre-complete the synthesis / final-answer item.** If your list ends with a "Synthesize findings", "Draft answer", "Write response" item, KEEP it "in_progress" while you generate the final assistant text. Do NOT call todo_write to mark it "completed" before emitting the answer. Reason: the system auto-clears the stored list the moment every item is "completed", flipping the user's progress bar to 0/0 during the answer stream — users read that as task abandonment. The natural end of turn (assistant text emitted, no further tool calls) is the completion signal; you do not need a final all-completed todo_write for the user to see the result.

Do-not-give-up rule (CRITICAL for multi-deliverable tasks):
- Once a todo list is in place, work through every item in order in the SAME turn. Do not stop after the first 1-2 items saying "let me continue with the rest" — the user sees that as an abandoned task.
- If an item fails (tool error, validation failure), mark it "failed" in the next todo_write call with a short error note, then move on to the next item. Partial completion with clear failures is fine; silent drop-outs are not.
- At end of turn, every research/work todo item must be "completed" or "failed" — EXCEPT the final synthesis/answer-writing item, which stays "in_progress" so the progress bar remains visible during the final response stream (see rule 7). No items should be left in "pending".
"""
