"""
Planner — deliberate-reasoning "think → plan → act" loop.

Produces structured ``ExecutionPlan`` objects that the agentic loop walks
step-by-step. The plan doubles as a user-facing TODO checklist: step status
transitions (pending → in_progress → completed/failed) are emitted as
synthetic ``update_plan`` tool calls so ``@assistant-ui/react`` can render
them with ``makeAssistantToolUI``.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass
class PlanStep:
    """A single step in an execution plan."""
    step_number: int
    description: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"                                           
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": f"step-{self.step_number}",
            "step_number": self.step_number,
            "description": self.description,
            "status": self.status,
            "tool_calls": self.tool_calls,
            "result": self.result,
            "error": self.error,
        }

@dataclass
class ExecutionPlan:
    """A full execution plan."""
    plan_id: str
    goal: str
    steps: List[PlanStep]
    created_at: float = field(default_factory=time.time)
    current_step: int = 0
    status: str = "pending"                                           
    reasoning: Optional[str] = None

    def get_next_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def mark_step_in_progress(self, step_number: int) -> None:
        for step in self.steps:
            if step.step_number == step_number:
                step.status = "in_progress"
                return

    def mark_step_complete(self, step_number: int, result: str) -> None:
        for step in self.steps:
            if step.step_number == step_number:
                step.status = "completed"
                step.result = result
                return

    def mark_step_failed(self, step_number: int, error: str) -> None:
        for step in self.steps:
            if step.step_number == step_number:
                step.status = "failed"
                step.error = error
                return

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for the ``update_plan`` synthetic tool call."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "status": self.status,
            "current_step": self.current_step,
            "steps": [s.to_dict() for s in self.steps],
            "reasoning": self.reasoning,
        }

_PLAN_SYSTEM_PROMPT_DEFAULT = """You are a planning agent. Your job is to decompose
a user request into a concise, ordered plan the execution agent can follow step
by step.

OUTPUT STRICTLY as JSON (no prose, no fences):
{
  "reasoning": "One or two sentences on your approach.",
  "steps": [
    {"description": "short imperative (e.g., 'Find relevant statutes')"},
    {"description": "..."}
  ]
}

Rules:
- 3-7 steps. Each step independent and concrete.
- Last step must synthesize/deliver the result.
- Don't list tools explicitly; the executor picks tools per step.
- Legal work: prefer clause-by-clause, jurisdiction-parallel, or fact-vs-law splits.
- If the task is trivial (single lookup, one-line reply), emit ONE step.
"""

_PLAN_SYSTEM_PROMPT_LEGAL_RESEARCH = """You are a legal research planning agent.
Your only job is to decompose the user's legal question into a focused research
plan. The executor has a /research skill that knows HOW to research each
dimension — your job is to pick WHICH dimensions and in what order.

OUTPUT STRICTLY as JSON (no prose, no code fences):
{
  "reasoning": "One sentence on how you split the question.",
  "steps": [
    {"description": "short imperative focused on ONE research dimension"},
    ...
  ]
}

DIMENSIONS — pick only those the question actually needs:

1. STATUTORY FRAMEWORK — the controlling statute(s), sections, provisions.
   Use when the question hinges on a specific law or regulation.
2. CASE LAW / PRECEDENT — how courts in the jurisdiction interpret the statute.
   Use when interpretation is contested or the statute uses open-textured
   terms ("reasonable", "material", "good faith").
3. REGULATORY GUIDANCE — regulator notes, circulars, no-action letters,
   codes of conduct. Use for regulated activities (securities, data, banking).
4. MARKET PRACTICE — what sophisticated parties actually draft, accept, or
   negotiate. Use when the question is about norms or "standard" terms.
5. JURISDICTION VARIATION — the same question under different legal systems.
   Use ONLY when the question names >1 jurisdiction, or when the user is
   clearly evaluating a cross-border situation.
6. RISK / COMMERCIAL — failure modes, remedies, damages, enforcement in
   practice. Use when the user cares about what happens in the real world,
   not just the black-letter rule.

RULES:
- 3-6 steps total. Trivial definitional questions ("what is estoppel?") get
  ONE step.
- One dimension per step. Do not combine "statute + case law" in one step.
- The LAST step is ALWAYS synthesis: pull the prior dimensions into a final
  answer for the user with inline citations.
- Match the user's language. If they asked in Russian, write step descriptions
  in Russian.
- Do NOT name specific tools. The executor picks tools from the /research
  skill.
- Do NOT include citation rules or formatting. The system prompt handles
  those.

EXAMPLES:

User: "Can unpaid shares be transferred in Malaysia?"
→ {
    "reasoning": "Single-jurisdiction question; needs statute + SSM guidance + market practice, then synthesis.",
    "steps": [
      {"description": "Find Malaysian Companies Act 2016 provisions on share transfer and unpaid share liability (e.g., Section 106, 192)"},
      {"description": "Find SSM regulatory guidance on share transfer registration and Form 32A filing requirements"},
      {"description": "Identify market practice: private company constitutions and shareholders' agreement provisions on transfer of unpaid shares"},
      {"description": "Synthesize: direct answer on transferability, liability consequences, and practical steps, with inline citations"}
    ]
  }

User: "Is a 12-month fees liability cap market-standard for UK SaaS contracts?"
→ {
    "reasoning": "Market-practice question with statute layer (UCTA/CRA reasonableness) and UK case law on LoL clauses.",
    "steps": [
      {"description": "Research UK statutory constraints on liability caps: Unfair Contract Terms Act 1977 and Consumer Rights Act 2015 reasonableness tests"},
      {"description": "Research UK case law on liability caps enforceability in B2B SaaS context (e.g., Watford Electronics, Regus)"},
      {"description": "Research UK SaaS market practice: typical multipliers for liability caps in enterprise SaaS"},
      {"description": "Synthesize: is 12-month-fees market standard? with inline citations"}
    ]
  }

User: "What is promissory estoppel?"
→ {
    "reasoning": "Definitional — no decomposition needed.",
    "steps": [
      {"description": "Provide a concise definition, elements, and jurisdictional note, with one authoritative citation"}
    ]
  }
"""

_PLAN_TEMPLATES = {
    "default": _PLAN_SYSTEM_PROMPT_DEFAULT,
    "legal_research": _PLAN_SYSTEM_PROMPT_LEGAL_RESEARCH,
}

class Planner:
    """Creates and manages execution plans backed by a real LLM call."""

    def __init__(self):
        self.plans: Dict[str, ExecutionPlan] = {}
        logger.info("Planner initialized")

    async def create_plan(
        self,
        goal: str,
        context: str = "",
        available_tools: Optional[List[str]] = None,
        session_state=None,
        model: Optional[str] = None,
        plan_template: str = "default",
    ) -> ExecutionPlan:
        """
        Generate a plan via LLM and return it. Caches under ``self.plans``
        keyed by plan_id.

        Args:
            plan_template: Which planning template to use. "default" is
                domain-agnostic; "legal_research" specializes the planner
                around legal dimensions (statute / case law / regulatory /
                market practice / jurisdiction variation / risk).
        """
        plan_id = f"plan-{int(time.time() * 1000)}"

        try:
            plan_json = await self._generate_plan_with_llm(
                goal=goal,
                context=context,
                available_tools=available_tools or [],
                model=model,
                plan_template=plan_template,
            )
            steps = self._parse_json_plan(plan_json)
            reasoning = plan_json.get("reasoning")
        except Exception as e:
            logger.warning(f"Planner LLM call failed ({e}); falling back to a single-step plan")
            steps = [PlanStep(step_number=1, description=goal)]
            reasoning = None

        if not steps:
            steps = [PlanStep(step_number=1, description=goal)]

        plan = ExecutionPlan(
            plan_id=plan_id,
            goal=goal,
            steps=steps,
            reasoning=reasoning,
        )
        self.plans[plan_id] = plan
        logger.info(f"Planner: created {plan_id} with {len(steps)} steps")
        return plan

    async def _generate_plan_with_llm(
        self,
        goal: str,
        context: str,
        available_tools: List[str],
        model: Optional[str] = None,
        plan_template: str = "default",
    ) -> Dict[str, Any]:
        """
        Ask the configured chat model to emit a JSON plan. Uses the same
        provider config the main agent uses — no new secrets required.
        """
        from openai import AsyncOpenAI
        from anylegal_oss.core.llm_provider import llm_provider

        provider_config = llm_provider.get_provider_config("chat")
        if not provider_config:
            raise RuntimeError("LLM provider not configured")

        from anylegal_oss.core.pricing import get_model_registry
        chosen_model = (
            model
            or os.getenv("PLANNER_MODEL")
            or os.getenv("CHAT_MODEL")
            or get_model_registry().get_default_model()
        )

        system_prompt = _PLAN_TEMPLATES.get(plan_template, _PLAN_SYSTEM_PROMPT_DEFAULT)

        user_prompt = f"Goal: {goal}\n\n"
        if context:
            user_prompt += f"Context: {context}\n\n"

        if available_tools and plan_template == "default":
            user_prompt += f"Available tools (for awareness; do not name them): {', '.join(available_tools)}\n\n"
        user_prompt += "Emit the plan JSON now."

        async with AsyncOpenAI(
            api_key=provider_config["api_key"],
            base_url=provider_config["base_url"],
            default_headers=provider_config.get("default_headers", {}),
            timeout=60.0,
        ) as client:

            try:
                response = await client.chat.completions.create(
                    model=chosen_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                logger.debug(f"Planner: response_format rejected ({e}); retrying without")
                response = await client.chat.completions.create(
                    model=chosen_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    max_tokens=1024,
                    temperature=0.2,
                )

        try:
            message = response.choices[0].message
        except Exception as e:
            raise RuntimeError(f"Planner: bad response shape: {e}")

        raw = ""
        for attr in ("content", "reasoning_content", "reasoning"):
            val = getattr(message, attr, None)
            if isinstance(val, str) and val.strip():
                raw = val
                break
        if not raw:
            raise RuntimeError("Planner: empty LLM response (no content/reasoning)")

        return self._extract_json(raw)

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Pull the first JSON object from text, tolerating ```json fences."""
        stripped = text.strip()

        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if fence:
            stripped = fence.group(1)

        if not stripped.startswith("{"):
            m = re.search(r"\{.*\}", stripped, re.DOTALL)
            if m:
                stripped = m.group(0)
        return json.loads(stripped)

    def _parse_json_plan(self, data: Dict[str, Any]) -> List[PlanStep]:
        raw_steps = data.get("steps") or []
        if not isinstance(raw_steps, list):
            return []
        parsed: List[PlanStep] = []
        for i, s in enumerate(raw_steps, start=1):
            if not isinstance(s, dict):
                continue
            desc = str(s.get("description", "")).strip()
            if not desc:
                continue
            parsed.append(PlanStep(step_number=i, description=desc))
        return parsed

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        return self.plans.get(plan_id)

    def complete_plan(self, plan_id: str, final_result: Optional[str] = None) -> None:
        plan = self.plans.get(plan_id)
        if not plan:
            return
        plan.status = "completed"

        for step in plan.steps:
            if step.status == "pending":
                step.status = "completed"

    def fail_plan(self, plan_id: str, error: str) -> None:
        plan = self.plans.get(plan_id)
        if plan:
            plan.status = "failed"
            logger.error(f"Plan {plan_id} failed: {error}")

planner = Planner()

def get_planner() -> Planner:
    return planner
