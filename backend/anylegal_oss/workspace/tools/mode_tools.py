"""
Mode-transition tools — plan-mode entry/exit.

Both tools are **permission-gated at the agent loop level, not inside the
executor**: when the model emits one of them, the agent yields a tool_call
event and ends the stream. The next client request carries the user's
approve/reject decision, which drives mode transitions and any follow-up
LLM call.

The handlers below are stubs — the executor is never meant to run them;
they're wired into the tool registry so the schemas surface in the LLM's
tool pool. If one *does* reach the executor (e.g. a refactor regression),
the stub returns an error rather than silently succeeding.
"""

from typing import Any, Dict

ENTER_PLAN_MODE_TOOL = {
    "name": "enter_plan_mode",
    "description": """Propose entering plan mode for the current task. Plan mode is a user-gated workflow: the user approves entering plan mode, you explore with a restricted read-only + research tool pool, then you call exit_plan_mode with a full plan for a second approval before execution.

## When to call this tool

**Always call it when the user's message contains any of these phrases (case-insensitive):**
- "deep research", "deep-research", "research deeply", "thoroughly research"
- "plan this", "plan it", "plan this out", "make a plan"
- "think step by step", "think step-by-step"
- "let's plan", "plan first", "plan before"
- "use plan mode", "enter plan mode"

These are explicit user requests for the planning workflow — respect the signal even if the question seems simple. Do NOT substitute todo_write when the user asks for plan mode; they want the approval gate and tool restrictions, not a lightweight progress list.

**Call it based on judgment when:**
- The task spans multiple legal issues (e.g. "analyze directors' duties across SG/UK/DE").
- Contract reviews spanning many clauses or where the approach isn't obvious.
- Research questions with multiple dimensions (statute, case law, regulatory, market practice).
- Document drafting involving non-trivial decisions about structure or approach.
- Multiple viable approaches exist and the trade-offs matter.

**Do NOT call it for:**
- Single-jurisdiction factual lookups answerable with ≤2 tool calls.
- Trivial questions answerable from your training data.
- Conversational exchanges that don't require tool use.
- Pure slash-command messages like "/research" alone (those just load a skill).

## Timing

Call enter_plan_mode AS SOON AS you have enough context to know planning is needed. You MAY do one or two light exploratory reads first (e.g. list_documents, or read the specific file the user referenced) to understand what the task is about — but do NOT execute research sweeps or tools that would produce the answer before proposing plan mode. Do not call any state-mutating tool (edit_document, create_document, run_code, add_comment, accept_all_changes, reject_all_changes) before entering plan mode.

## Protocol

1. You call enter_plan_mode(reason=<one sentence>).
2. The stream ends; the user sees an approval dialog with your reason.
3. On approval, your NEXT turn begins in plan mode: restricted tool pool (read-only + research + todo_write + exit_plan_mode), additional plan-mode instructions injected as a tool_result.
4. On rejection, your next turn continues reactively with a decline tool_result injected — answer the question directly.

## Reason field

One sentence, concrete. Shown verbatim to the user. Good: "Multi-jurisdictional director duty analysis across SG/UK/DE requires comparing statutory and market-practice dimensions." Bad: "This is complex.""",
    "input_schema": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": (
                    "One concrete sentence explaining why this task "
                    "warrants plan mode. Shown verbatim to the user in "
                    "the approval dialog."
                ),
            },
        },
        "required": ["reason"],
    },
}

EXIT_PLAN_MODE_TOOL = {
    "name": "exit_plan_mode",
    "description": """Use this tool ONLY when you are in plan mode and have finished composing your plan and are ready for user approval.

## How This Tool Works
- The ``plan`` argument is the COMPLETE plan as markdown. The user reads it verbatim in an approval card.
- This tool ends your turn. The stream stops and waits for the user's decision.
- On approval: the plan is injected into your context under "## Approved Plan:" as a tool_result, session mode flips back to default, and you continue in the next turn with the full tool pool to execute the plan.
- On rejection: you stay in plan mode. Refine the plan based on any follow-up message and call exit_plan_mode again.

## Required Plan Structure (markdown)
1. **Goal** — one sentence stating what you will deliver.
2. **Steps** — ordered list. For each step, name the tool(s) you will use and what you expect to learn.
3. **Assumptions / open questions** — anything the user should clarify before you proceed.
4. **Deliverable** — the final shape (memo, redlined DOCX, table, email draft, etc.) + approximate length.

## Strict Rules
- **Do NOT write the user's answer in plan mode.** Prose content you emit during plan mode is NOT shown to the user. Only the ``plan`` argument passed here reaches them.
- **exit_plan_mode MUST be the last tool you call in this turn.** Do not call other tools after it.
- **Do not call exit_plan_mode when not in plan mode.** If you are in default mode, the call is invalid and will be rejected.
- **Do not ask "is this plan okay?" via another tool.** This tool itself requests approval.

## Example (structure, not content)
```json
{
  "plan": "# Research Plan: Can a Singapore Pte Ltd accept crypto as share capital?\\n\\n## Goal\\nDetermine whether cryptocurrency qualifies as valid consideration under Companies Act 1967.\\n\\n## Steps\\n1. web_search + web_fetch → Companies Act 1967 (SG) — sections on share capital and consideration\\n2. web_search + web_fetch → MAS PSA guidance on DPTs\\n3. web_search → SG case law on crypto as property (B2C2 v Quoine, CLM v CLN)\\n4. Synthesize into a memo covering permissibility, valuation, ACRA compliance, alternatives\\n\\n## Open questions\\n- Is the issuer a public or private company?\\n- Target investor citizenship (affects FSMA DTSP licensing)?\\n\\n## Deliverable\\nMarkdown memo, ~600 words, with inline citations and a recommendations table."
}
```

## Anti-patterns (do NOT do these)
- ❌ Writing the final answer/memo body as prose and calling exit_plan_mode with only a one-line plan.
- ❌ Calling exit_plan_mode without having explored the question first.
- ❌ Calling it when session mode is 'default' (returns a validation error).
- ❌ Using ask_user_question to request plan approval — this tool IS the approval gate.
""",
    "input_schema": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "string",
                "description": "The complete plan as markdown. See tool description for required structure.",
            },
        },
        "required": ["plan"],
    },
}

def enter_plan_mode_stub(**_: Any) -> Dict[str, Any]:
    """Executor should never call this — the agent loop intercepts."""
    return {
        "success": False,
        "error": (
            "enter_plan_mode must be intercepted by the agent loop and "
            "gated on user approval; it should not reach the executor."
        ),
    }

def exit_plan_mode_stub(**_: Any) -> Dict[str, Any]:
    """Executor should never call this — the agent loop intercepts."""
    return {
        "success": False,
        "error": (
            "exit_plan_mode must be intercepted by the agent loop and "
            "gated on user approval; it should not reach the executor."
        ),
    }

MODE_TOOLS = {
    "enter_plan_mode": enter_plan_mode_stub,
    "exit_plan_mode": exit_plan_mode_stub,
}

ENTER_PLAN_MODE_GUIDANCE = ""

PLAN_MODE_ENTRY_RESULT = """\
Entered plan mode. You should now focus on exploring the question and designing an approach.

In plan mode, you should:
1. Thoroughly explore the question — read any relevant workspace documents, run web_search and web_fetch for statutory and market-practice detail, and use todo_write to track sub-steps if the work decomposes.
2. Identify the dimensions that matter for this question (statute / case law / regulatory / market practice / jurisdiction / risk) and consider multiple approaches where applicable.
3. Surface any ambiguity via ask_client before committing to an approach.
4. When your plan is complete, call exit_plan_mode with the full plan markdown as the ``plan`` argument.

CRITICAL RULES:
- DO NOT write the final answer, memo, or deliverable in this turn. Prose content you emit during plan mode is NOT shown to the user — only the ``plan`` argument you pass to exit_plan_mode is surfaced in the approval card. The actual answer is produced in the NEXT turn, after the user approves the plan.
- DO NOT call any tool that modifies state — edit_document, create_document, run_code, add_comment, accept_all_changes, reject_all_changes. These are deliberately withheld from your tool pool in plan mode. Attempting them is a bug.
- DO call tools that fail-retry on errors — if a tool returns an error, fall back to a different tool covering the same question. Do not retry the same tool twice.
- END your turn by calling exit_plan_mode. That is the only valid terminal action in plan mode.

Remember: you're planning, not executing. The user approves the plan first; execution happens in the next turn with the plan injected as context.
"""

PLAN_MODE_GUIDANCE = "You are in plan mode. See the `exit_plan_mode` tool description for the rules that apply until you exit."

LEGAL_RESEARCH_PLAN_HINT = """\
For legal research plans, decompose along dimensions the user will verify: applicable statutes, relevant case law, regulatory guidance, market practice, and jurisdiction-specific nuances. If the question spans multiple jurisdictions, add a comparative synthesis step.
"""

EXIT_PLAN_MODE_NOT_IN_PLAN_MODE_ERROR = (
    "You are not in plan mode. exit_plan_mode is only valid when the "
    "session is in plan mode (after an approved enter_plan_mode). If "
    "your plan was already approved, continue with execution using the "
    "full tool pool — do not call exit_plan_mode again."
)
