"""
Services for the Document Editor module.

Provides clause analysis, redline generation, playbook management,
and document diff/comparison using the existing Anylegal LLM infrastructure.
"""

import json
import logging
import os
import re
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path

DIFF_AVAILABLE = False
_diff_match_patch_class = None

try:
    from diff_match_patch import diff_match_patch as _dmp_class
    _diff_match_patch_class = _dmp_class
    DIFF_AVAILABLE = True
    logging.info("✅ diff-match-patch library loaded successfully")
except ImportError as e:
    logging.warning(f"⚠️ diff-match-patch not available: {e}")
except Exception as e:
    logging.error(f"❌ Error loading diff-match-patch: {e}")

from . import db
from .models import ClauseAnalysis, RedlineSuggestion

logger = logging.getLogger(__name__)

LLM_AVAILABLE = False
_llm_provider = None
_llm_client = None

try:
    from anylegal_oss.core.llm_provider import LLMProviderConfig

    _llm_provider = LLMProviderConfig()
    _llm_client = _llm_provider.create_sync_client(model_type="chat")
    LLM_AVAILABLE = True
    logger.info("✅ Document editor LLM integration initialized")
except Exception as e:
    logger.warning(f"⚠️ LLM integration not available: {e}")
    LLM_AVAILABLE = False

def get_llm_client():
    """Get the LLM client for document editor."""
    global _llm_client, _llm_provider
    if _llm_client is None and LLM_AVAILABLE:
        _llm_client = _llm_provider.create_sync_client(model_type="chat")
    return _llm_client

def get_chat_model(model_override: Optional[str] = None) -> str:
    """Get the chat model name, with optional override."""
    if model_override:
        return model_override
    if _llm_provider:
        return _llm_provider.chat_model or "deepseek-ai/DeepSeek-V3"
    return os.getenv("CHAT_MODEL", "deepseek-ai/DeepSeek-V3")

def parse_llm_json(content: str, fallback: Any = None) -> Any:
    """
    Robustly parse JSON from LLM response, handling various model quirks.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Extra text before/after JSON
    - Thinking blocks (<think>...</think>)
    - Multiple JSON objects (takes first valid one)
    """
    if not content:
        return fallback

    original_content = content

    import re
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<thinking>.*?</thinking>', '', content, flags=re.DOTALL | re.IGNORECASE)

    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")

        if lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    brace_start = content.find('{')
    if brace_start != -1:

        depth = 0
        for i, char in enumerate(content[brace_start:], brace_start):
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    json_str = content[brace_start:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                    break

    bracket_start = content.find('[')
    if bracket_start != -1:
        depth = 0
        for i, char in enumerate(content[bracket_start:], bracket_start):
            if char == '[':
                depth += 1
            elif char == ']':
                depth -= 1
                if depth == 0:
                    json_str = content[bracket_start:i+1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                    break

    cleaned = re.sub(r',(\s*[}\]])', r'\1', content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    logger.warning(f"Failed to parse JSON from LLM response: {original_content[:500]}...")
    return fallback

def get_provider_extra_body(model_id: Optional[str] = None) -> dict:
    """
    Get the extra_body dict with provider preferences for OpenRouter.

    Args:
        model_id: Optional model ID for model-specific provider order.
                  If provided and model has preferred_providers, uses those.
                  Otherwise falls back to global CHAT provider order.
    """

    if model_id:
        try:
            from anylegal_oss.core.pricing import get_model_registry
            registry = get_model_registry()
            if registry:
                model_prefs = registry.get_model_provider_preferences(model_id)
                if model_prefs:
                    logger.info(f"Using model-specific providers for {model_id}: {model_prefs['order']}")
                    return {"provider": model_prefs}
        except Exception as e:
            logger.warning(f"Could not get model-specific providers: {e}")

    if _llm_provider:
        prefs = _llm_provider.get_openrouter_provider_preferences(model_type="chat")
        if prefs:
            return {"provider": prefs}
    return {}

class PromptLoader:
    """Load prompt templates for document editing operations."""

    def __init__(self):
        self.prompts_dir = Path(__file__).parent / "prompts"
        self.prompts_dir.mkdir(exist_ok=True)
        self._cache = {}

    def load(self, prompt_name: str, **kwargs) -> str:
        """Load and format a prompt template."""
        if prompt_name not in self._cache:
            prompt_path = self.prompts_dir / f"{prompt_name}.md"
            if prompt_path.exists():
                self._cache[prompt_name] = prompt_path.read_text(encoding='utf-8')
            else:

                self._cache[prompt_name] = self._get_inline_prompt(prompt_name)

        template = self._cache[prompt_name]

        try:
            return template.format(**kwargs)
        except KeyError as e:
            logger.warning(f"Missing template variable: {e}")
            return template

    def _get_inline_prompt(self, prompt_name: str) -> str:
        """Get inline fallback prompts."""
        prompts = {
            "analyze_clause": ANALYZE_CLAUSE_PROMPT,
            "generate_redlines": GENERATE_REDLINES_PROMPT,
            "detect_clause_type": DETECT_CLAUSE_TYPE_PROMPT
        }
        return prompts.get(prompt_name, "")

ANALYZE_CLAUSE_PROMPT = """You are a legal contract analyst. Analyze this contract clause.

CLAUSE TEXT:
{clause_text}

SURROUNDING CONTEXT:
{context}

REPRESENTING PARTY: {representing}
CONTRACT TYPE: {contract_type}
JURISDICTION: {jurisdiction}

Analyze the clause and respond in JSON format:
{{
  "clause_type": "indemnification" | "limitation_of_liability" | "termination" | "confidentiality" | "warranty" | "representations" | "governing_law" | "dispute_resolution" | "force_majeure" | "assignment" | "other",
  "position": "favorable" | "balanced" | "unfavorable",
  "risk_level": "low" | "medium" | "high" | "critical",
  "issues": ["issue 1", "issue 2"],
  "summary": "Brief explanation of the clause and its implications for {representing}"
}}

Consider:
1. How does this clause affect the {representing}'s interests?
2. Are there any unusual or concerning provisions?
3. Is the language standard or does it deviate from market practice?
4. Are there any enforceability concerns in {jurisdiction}?"""

GENERATE_REDLINES_PROMPT = """You are a legal contract reviewer representing the {representing}.

CLAUSE TO REVIEW:
{clause_text}

CONTEXT:
{context}

CONTRACT TYPE: {contract_type}
JURISDICTION: {jurisdiction}

{playbook_context}

Generate redline suggestions to protect the {representing}'s interests.

Respond in JSON format:
{{
  "suggestions": [
    {{
      "original": "exact text from the clause to replace",
      "suggested": "replacement text",
      "explanation": "why this change protects {representing}",
      "priority": "high" | "medium" | "low"
    }}
  ]
}}

IMPORTANT GUIDELINES:
1. Only suggest changes that are legally substantive (not just stylistic)
2. Suggestions should be reasonable and likely to be accepted in negotiation
3. Focus on protecting {representing}'s key interests
4. Ensure suggested language is legally valid in {jurisdiction}
5. Keep the "original" text as short as possible while being unique
6. Maximum {max_suggestions} suggestions, prioritize the most impactful changes
7. If fewer changes are truly needed, return fewer - quality over quantity"""

DETECT_CLAUSE_TYPE_PROMPT = """Identify the type of this contract clause.

CLAUSE:
{clause_text}

Respond with ONLY the clause type from this list:
- indemnification
- limitation_of_liability
- termination
- confidentiality
- warranty
- representations
- governing_law
- dispute_resolution
- force_majeure
- assignment
- entire_agreement
- amendment
- notice
- severability
- other

Response (single word only):"""

class ClauseAnalyzer:
    """Analyze contract clauses using LLM."""

    def __init__(self):
        self.prompt_loader = PromptLoader()

    def analyze(
        self,
        text: str,
        context: str = "",
        representing: str = "buyer",
        document_type: str = "general",
        jurisdiction: str = "GENERAL",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze a clause and return risk assessment.

        Args:
            text: The clause text to analyze
            context: Surrounding text for context
            representing: Party being represented
            document_type: Type of contract
            jurisdiction: Applicable jurisdiction
            model: Optional model override (user's preferred model)

        Returns:
            Dict with clause_type, position, risk_level, issues, summary
        """
        if not LLM_AVAILABLE:
            return self._fallback_analysis(text, representing)

        prompt = self.prompt_loader.load(
            "analyze_clause",
            clause_text=text,
            context=context or "Not provided",
            representing=representing,
            contract_type=document_type or "general",
            jurisdiction=jurisdiction
        )

        try:
            client = get_llm_client()
            effective_model = get_chat_model(model)

            response = client.chat.completions.create(
                model=effective_model,
                messages=[
                    {"role": "system", "content": "You are a legal contract analyst. Respond only in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000,
                extra_body=get_provider_extra_body(effective_model)
            )

            content = response.choices[0].message.content

            result = parse_llm_json(content)

            if not result:
                logger.error(f"Failed to parse analysis response from {effective_model}")
                return self._fallback_analysis(text, representing)

            result = self._normalize_analysis(result)

            logger.info(f"Clause analyzed with {effective_model}: type={result.get('clause_type')}, risk={result.get('risk_level')}")
            return result

        except Exception as e:
            logger.error(f"Clause analysis failed: {e}")
            return self._fallback_analysis(text, representing)

    def detect_clause_type(self, text: str) -> str:
        """Quick clause type detection without full analysis."""
        if not LLM_AVAILABLE:
            return self._heuristic_clause_type(text)

        prompt = self.prompt_loader.load(
            "detect_clause_type",
            clause_text=text[:1000]                   
        )

        try:
            client = get_llm_client()
            model = get_chat_model()

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=20,
                extra_body=get_provider_extra_body(model)
            )

            clause_type = response.choices[0].message.content.strip().lower()

            clause_type = clause_type.replace("-", "_").strip()
            return clause_type if clause_type else "other"

        except Exception as e:
            logger.error(f"Clause type detection failed: {e}")
            return self._heuristic_clause_type(text)

    def _normalize_analysis(self, result: Dict) -> Dict:
        """Normalize and validate analysis result."""
        valid_types = {
            "indemnification", "limitation_of_liability", "termination",
            "confidentiality", "warranty", "representations", "governing_law",
            "dispute_resolution", "force_majeure", "assignment", 
            "entire_agreement", "amendment", "notice", "severability", "other"
        }
        valid_positions = {"favorable", "balanced", "unfavorable"}
        valid_risks = {"low", "medium", "high", "critical"}

        return {
            "clause_type": result.get("clause_type", "other") 
                if result.get("clause_type") in valid_types else "other",
            "position": result.get("position", "balanced")
                if result.get("position") in valid_positions else "balanced",
            "risk_level": result.get("risk_level", "medium")
                if result.get("risk_level") in valid_risks else "medium",
            "issues": result.get("issues", []) if isinstance(result.get("issues"), list) else [],
            "summary": result.get("summary", "Analysis completed.")
        }

    def _fallback_analysis(self, text: str, representing: str) -> Dict:
        """Fallback analysis when LLM is unavailable."""
        clause_type = self._heuristic_clause_type(text)

        return {
            "clause_type": clause_type,
            "position": "balanced",
            "risk_level": "medium",
            "issues": ["LLM analysis unavailable - manual review recommended"],
            "summary": f"Detected {clause_type} clause. Manual review recommended."
        }

    def _heuristic_clause_type(self, text: str) -> str:
        """Simple keyword-based clause type detection."""
        text_lower = text.lower()

        patterns = [
            ("indemnif", "indemnification"),
            ("hold harmless", "indemnification"),
            ("limitation of liability", "limitation_of_liability"),
            ("liability shall not exceed", "limitation_of_liability"),
            ("cap on damages", "limitation_of_liability"),
            ("terminat", "termination"),
            ("confidential", "confidentiality"),
            ("non-disclosure", "confidentiality"),
            ("warrant", "warranty"),
            ("represent", "representations"),
            ("governing law", "governing_law"),
            ("jurisdiction", "governing_law"),
            ("arbitrat", "dispute_resolution"),
            ("dispute", "dispute_resolution"),
            ("force majeure", "force_majeure"),
            ("act of god", "force_majeure"),
            ("assign", "assignment"),
            ("entire agreement", "entire_agreement"),
            ("amend", "amendment"),
            ("notice", "notice"),
            ("sever", "severability"),
        ]

        for pattern, clause_type in patterns:
            if pattern in text_lower:
                return clause_type

        return "other"

class RedlineGenerator:
    """Generate redline suggestions for contract clauses."""

    def __init__(self):
        self.prompt_loader = PromptLoader()
        self.analyzer = ClauseAnalyzer()

    def generate(
        self,
        text: str,
        representing: str = "the reviewing party",
        context: str = "",
        document_type: str = "general",
        jurisdiction: str = "GENERAL",
        apply_playbook: bool = True,
        user_id: Optional[int] = None,
        full_document: Optional[str] = None,
        main_instruction: Optional[str] = None,
        clause_instruction: Optional[str] = None,
        user_instructions: Optional[str] = None,                                                
        max_suggestions: int = 5,                                          
        model: Optional[str] = None                          
    ) -> Dict[str, Any]:
        """
        Generate redline suggestions for a clause.

        Args:
            text: Clause text to redline
            representing: Party being represented (legacy, prefer main_instruction)
            context: Surrounding text
            document_type: Type of contract
            jurisdiction: Applicable jurisdiction
            apply_playbook: Whether to apply user's playbook rules
            user_id: User ID for playbook lookup
            full_document: Complete document text for full context analysis
            main_instruction: Session-level instruction (who you represent, risk posture, deal context)
                              This goes into the system message and persists across analyses.
            clause_instruction: Per-analysis instruction (specific focus for this clause)
                               This is ephemeral and changes with each analysis.
            user_instructions: Legacy single instructions field (used if main_instruction not provided)
            max_suggestions: Maximum number of suggestions to return (default 5)

        Returns:
            Dict with analysis and suggestions
        """

        effective_context = full_document if full_document else context

        effective_main = main_instruction or user_instructions or ""

        clause_section = ""
        if clause_instruction:
            clause_section = f"""
## ADDITIONAL FOCUS FOR THIS CLAUSE
{clause_instruction}
"""

        analysis = self.analyzer.analyze(
            text=text,
            context=effective_context,
            representing=representing,
            document_type=document_type,
            jurisdiction=jurisdiction,
            model=model
        )

        playbook_context = ""
        playbook_matches = []

        if apply_playbook and user_id:
            playbook_service = PlaybookService(user_id)
            playbook_result = playbook_service.get_relevant_context(
                clause_text=text,
                clause_type=analysis.get("clause_type"),
                contract_type=document_type,
                jurisdiction=jurisdiction
            )
            playbook_context = playbook_result.get("prompt_section", "")
            playbook_matches = playbook_result.get("matches", [])

        if not LLM_AVAILABLE:
            return {
                "analysis": analysis,
                "suggestions": [],
                "playbook_matches": playbook_matches,
                "error": "LLM unavailable"
            }

        if full_document:

            doc_text = full_document[:100000] if len(full_document) > 100000 else full_document
            context_section = f"""## FULL AGREEMENT TEXT
The following is the complete agreement text. Use this to understand definitions, 
related clauses, and the overall structure. The clause being analyzed is marked with >>> and <<<.

{doc_text}

---
END OF FULL AGREEMENT
---"""
        else:
            context_section = context or "Not provided"

        combined_context = playbook_context
        if clause_section:
            combined_context = f"{clause_section}\n\n{playbook_context}"

        prompt = self.prompt_loader.load(
            "generate_redlines",
            clause_text=text,
            context=context_section,
            representing=representing,
            contract_type=document_type or "general",
            jurisdiction=jurisdiction,
            playbook_context=combined_context,
            max_suggestions=max_suggestions
        )

        system_instruction = "You are a senior legal counsel reviewing contract clauses."
        if effective_main:
            system_instruction = f"""You are a senior legal counsel reviewing contract clauses.

## SESSION CONTEXT (applies to all analyses in this session)
{effective_main}

Follow these instructions for all clause reviews in this session."""

        system_instruction += "\n\nRespond only in valid JSON."

        try:
            client = get_llm_client()
            effective_model = get_chat_model(model)

            response = client.chat.completions.create(
                model=effective_model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000,
                extra_body=get_provider_extra_body(effective_model)
            )

            content = response.choices[0].message.content

            result = parse_llm_json(content)

            if not result:
                logger.error(f"Failed to parse redline response from {effective_model}")
                return {
                    "analysis": analysis,
                    "suggestions": [],
                    "playbook_matches": playbook_matches,
                    "error": f"Failed to parse response from {effective_model}"
                }

            suggestions = self._normalize_suggestions(result.get("suggestions", []))

            logger.info(f"Generated {len(suggestions)} redline suggestions using {effective_model}")

            return {
                "analysis": analysis,
                "suggestions": suggestions,
                "playbook_matches": playbook_matches,
                "model_used": effective_model
            }

        except Exception as e:
            logger.error(f"Redline generation failed with {model or 'default model'}: {e}")
            return {
                "analysis": analysis,
                "suggestions": [],
                "playbook_matches": playbook_matches,
                "error": str(e)
            }

    def _normalize_suggestions(self, suggestions: List[Dict]) -> List[Dict]:
        """Normalize and validate suggestions."""
        valid_priorities = {"low", "medium", "high"}
        normalized = []

        for s in suggestions:
            if not s.get("original") or not s.get("suggested"):
                continue

            normalized.append({
                "original": s.get("original", ""),
                "suggested": s.get("suggested", ""),
                "explanation": s.get("explanation", ""),
                "priority": s.get("priority", "medium") 
                    if s.get("priority") in valid_priorities else "medium",
                "source": "llm",
                "applied": False
            })

        priority_order = {"high": 0, "medium": 1, "low": 2}
        normalized.sort(key=lambda x: priority_order.get(x["priority"], 1))

        return normalized

class PlaybookService:
    """
    Manage user's playbook of clauses and rules.

    Priority for loading playbook:
    1. User's markdown file (playbooks/users/{user_id}.md)
    2. Database clauses (playbook_clauses table)
    3. Default playbook (playbooks/default-commercial.md)
    """

    def __init__(self, user_id: int, prefer_file: bool = True):
        """
        Initialize PlaybookService.

        Args:
            user_id: User ID
            prefer_file: If True, check markdown file before DB
        """
        self.user_id = user_id
        self._prefer_file = prefer_file
        self._loader = None
        self._cached_playbook = None

    @property
    def loader(self):
        """Lazy load PlaybookLoader."""
        if self._loader is None:
            try:
                from .playbooks import PlaybookLoader
                self._loader = PlaybookLoader()
            except ImportError:
                logger.warning("PlaybookLoader not available")
        return self._loader

    def get_playbook(self, include_default: bool = True):
        """
        Get the full parsed playbook.

        Returns:
            Playbook object or None
        """
        if self._cached_playbook is not None:
            return self._cached_playbook

        if self.loader:
            self._cached_playbook = self.loader.load_playbook(
                user_id=self.user_id,
                fallback_to_db=True,
                fallback_to_default=include_default
            )
            return self._cached_playbook
        return None

    def get_playbook_content(self) -> Optional[str]:
        """Get raw playbook markdown content."""
        playbook = self.get_playbook()
        return playbook.raw_content if playbook else None

    def has_file_playbook(self) -> bool:
        """Check if user has a markdown playbook file."""
        if self.loader:
            path = self.loader.get_playbook_path(self.user_id)
            return path.exists()
        return False

    def get_clauses(
        self,
        clause_type: Optional[str] = None,
        position: Optional[str] = None,
        jurisdiction: Optional[str] = None,
        contract_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        Get user's playbook clauses with optional filtering.

        If user has a markdown playbook file, parses clauses from there.
        Otherwise falls back to database.
        """

        if self._prefer_file and self.has_file_playbook():
            playbook = self.get_playbook(include_default=False)
            if playbook:
                return self._playbook_to_clauses(playbook, clause_type, position, limit)

        return db.get_playbook_clauses(
            user_id=self.user_id,
            clause_type=clause_type,
            position=position,
            jurisdiction=jurisdiction,
            contract_type=contract_type,
            limit=limit
        )

    def _playbook_to_clauses(
        self,
        playbook,
        clause_type: Optional[str],
        position: Optional[str],
        limit: int
    ) -> List[Dict]:
        """Convert parsed playbook to clause list format."""
        clauses = []

        for ct, clause in playbook.clauses.items():

            if clause_type and ct.lower() != clause_type.lower().replace('_', ' '):
                continue

            positions_map = [
                ("acceptable", clause.acceptable, "favorable"),
                ("requires_review", clause.requires_review, "balanced"),
                ("unacceptable", clause.unacceptable, "adverse"),
            ]

            for pos_name, items, db_position in positions_map:

                if position and db_position != position:
                    continue

                for i, item in enumerate(items):
                    clauses.append({
                        "id": f"file_{ct}_{pos_name}_{i}",
                        "clause_type": ct,
                        "position": db_position,
                        "title": f"{clause.title} - {pos_name.replace('_', ' ').title()}",
                        "clause_text": item,
                        "jurisdiction": playbook.metadata.jurisdiction,
                        "source": "file"
                    })

        return clauses[:limit]

    def get_clause(self, clause_id: int) -> Optional[Dict]:
        """Get a specific clause."""
        return db.get_playbook_clause_by_id(clause_id, self.user_id)

    def add_clause(self, clause_data: Dict) -> int:
        """Add a new clause to playbook."""
        return db.create_playbook_clause(
            user_id=self.user_id,
            clause_type=clause_data.get("clause_type", "other"),
            position=clause_data.get("position", "balanced"),
            title=clause_data.get("title", "Untitled"),
            clause_text=clause_data.get("clause_text", ""),
            explanation=clause_data.get("explanation"),
            jurisdiction=clause_data.get("jurisdiction", "GENERAL"),
            contract_type=clause_data.get("contract_type"),
            tags=clause_data.get("tags", [])
        )

    def update_clause(self, clause_id: int, updates: Dict) -> bool:
        """Update a clause."""
        return db.update_playbook_clause(clause_id, self.user_id, **updates)

    def delete_clause(self, clause_id: int) -> bool:
        """Delete a clause."""
        return db.delete_playbook_clause(clause_id, self.user_id)

    def record_clause_usage(self, clause_id: int) -> None:
        """Record that a clause was used (for sorting by popularity)."""
        db.increment_clause_usage(clause_id)

    def get_rules(
        self,
        rule_type: Optional[str] = None,
        trigger_clause_type: Optional[str] = None,
        is_active: bool = True,
        limit: int = 100
    ) -> List[Dict]:
        """Get user's playbook rules."""
        return db.get_playbook_rules(
            user_id=self.user_id,
            rule_type=rule_type,
            trigger_clause_type=trigger_clause_type,
            is_active=is_active,
            limit=limit
        )

    def add_rule(self, rule_data: Dict) -> int:
        """Add a new rule to playbook."""
        return db.create_playbook_rule(
            user_id=self.user_id,
            name=rule_data.get("name", "Untitled Rule"),
            rule_type=rule_data.get("rule_type", "always_flag"),
            action=rule_data.get("action", {}),
            description=rule_data.get("description"),
            trigger_clause_type=rule_data.get("trigger_clause_type"),
            trigger_keywords=rule_data.get("trigger_keywords", []),
            trigger_semantic=rule_data.get("trigger_semantic"),
            severity=rule_data.get("severity", "medium"),
            priority=rule_data.get("priority", 0),
            contract_types=rule_data.get("contract_types"),
            jurisdictions=rule_data.get("jurisdictions")
        )

    def update_rule(self, rule_id: int, updates: Dict) -> bool:
        """Update a rule."""
        return db.update_playbook_rule(rule_id, self.user_id, **updates)

    def delete_rule(self, rule_id: int) -> bool:
        """Delete a rule."""
        return db.delete_playbook_rule(rule_id, self.user_id)

    def get_relevant_context(
        self,
        clause_text: str,
        clause_type: Optional[str] = None,
        contract_type: Optional[str] = None,
        jurisdiction: Optional[str] = None
    ) -> Dict:
        """
        Get relevant playbook context for a clause.

        Returns matching rules and preferred clauses formatted
        for injection into LLM prompts.
        """

        matching_rules = db.get_matching_rules(
            user_id=self.user_id,
            clause_text=clause_text,
            clause_type=clause_type,
            contract_type=contract_type,
            jurisdiction=jurisdiction
        )

        preferred_clauses = []
        if clause_type:
            preferred_clauses = self.get_clauses(
                clause_type=clause_type,
                position="client_favorable",
                jurisdiction=jurisdiction,
                limit=3
            )

        prompt_parts = []

        if matching_rules:
            prompt_parts.append("## PLAYBOOK RULES TO APPLY")
            prompt_parts.append("")
            for rule in matching_rules[:5]:                        
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(rule["severity"], "⚪")
                prompt_parts.append(f"{severity_icon} **{rule['name']}** ({rule['severity']})")
                if rule.get("description"):
                    prompt_parts.append(f"   {rule['description']}")
                action = rule.get("action", {})
                if action.get("explanation"):
                    prompt_parts.append(f"   Action: {action['explanation']}")
                prompt_parts.append("")

        if preferred_clauses:
            prompt_parts.append("## PREFERRED CLAUSE LANGUAGE")
            prompt_parts.append("")
            for clause in preferred_clauses[:2]:                  
                prompt_parts.append(f"**{clause['title']}**")
                prompt_parts.append(f"```")
                prompt_parts.append(clause['clause_text'][:500])                         
                prompt_parts.append(f"```")
                if clause.get("explanation"):
                    prompt_parts.append(f"Why: {clause['explanation']}")
                prompt_parts.append("")

        return {
            "prompt_section": "\n".join(prompt_parts) if prompt_parts else "",
            "matches": {
                "rules": [{"id": r["id"], "name": r["name"], "severity": r["severity"]} for r in matching_rules],
                "clauses": [{"id": c["id"], "title": c["title"]} for c in preferred_clauses]
            }
        }

class DocumentDiffer:
    """
    Compare two document versions and generate inline-marked diff.

    Uses Google's diff-match-patch algorithm for precise character-level
    comparison, then formats output with inline markers for LLM review.

    Output format: [-deleted text-][+inserted text+]
    """

    def __init__(self):
        if not DIFF_AVAILABLE or _diff_match_patch_class is None:
            raise RuntimeError("diff-match-patch library not available")
        self.dmp = _diff_match_patch_class()

        self.dmp.Diff_Timeout = 0

    def compare(
        self, 
        original: str, 
        revised: str,
        semantic_cleanup: bool = True
    ) -> Dict[str, Any]:
        """
        Compare two document versions and return marked-up text.

        Args:
            original: Original document text
            revised: Revised document text
            semantic_cleanup: If True, apply semantic cleanup for cleaner diffs
                             (groups changes at word boundaries where sensible)

        Returns:
            Dict with:
                - marked_document: Full document with inline diff markers
                - stats: {insertions, deletions, unchanged_chars, changed_chars}
                - changes: List of individual changes with context
        """
        if not original and not revised:
            return {
                "marked_document": "",
                "stats": {"insertions": 0, "deletions": 0, "unchanged_chars": 0, "changed_chars": 0},
                "changes": []
            }

        if not original:
            return {
                "marked_document": f"[+{revised}+]",
                "stats": {"insertions": 1, "deletions": 0, "unchanged_chars": 0, "changed_chars": len(revised)},
                "changes": [{"type": "insertion", "text": revised[:200], "full_text": revised}]
            }
        if not revised:
            return {
                "marked_document": f"[-{original}-]",
                "stats": {"insertions": 0, "deletions": 1, "unchanged_chars": 0, "changed_chars": len(original)},
                "changes": [{"type": "deletion", "text": original[:200], "full_text": original}]
            }

        diffs = self.dmp.diff_main(original, revised)

        if semantic_cleanup:
            self.dmp.diff_cleanupSemantic(diffs)

        marked_parts = []
        changes = []
        stats = {
            "insertions": 0,
            "deletions": 0, 
            "unchanged_chars": 0,
            "changed_chars": 0
        }

        position = 0

        for op, text in diffs:
            if op == 0:         
                marked_parts.append(text)
                stats["unchanged_chars"] += len(text)
                position += len(text)
            elif op == -1:          
                marked_parts.append(f"[-{text}-]")
                stats["deletions"] += 1
                stats["changed_chars"] += len(text)
                changes.append({
                    "type": "deletion",
                    "text": text[:200] + ("..." if len(text) > 200 else ""),
                    "full_text": text,
                    "position": position
                })
            elif op == 1:          
                marked_parts.append(f"[+{text}+]")
                stats["insertions"] += 1
                stats["changed_chars"] += len(text)
                changes.append({
                    "type": "insertion", 
                    "text": text[:200] + ("..." if len(text) > 200 else ""),
                    "full_text": text,
                    "position": position
                })
                position += len(text)

        marked_document = "".join(marked_parts)

        return {
            "marked_document": marked_document,
            "stats": stats,
            "changes": changes
        }

    def compare_with_context(
        self,
        original: str,
        revised: str,
        context_chars: int = 100
    ) -> Dict[str, Any]:
        """
        Compare documents and add context around each change.

        This enriches each change with surrounding text for better
        LLM understanding of where changes occur in the document.
        """
        result = self.compare(original, revised)

        marked = result["marked_document"]

        for change in result["changes"]:
            pos = change.get("position", 0)

            start = max(0, pos - context_chars)
            end = min(len(original), pos + context_chars)

            change["context_before"] = original[start:pos].strip()[-context_chars:]
            change["context_after"] = original[pos:end].strip()[:context_chars]

        return result

    def get_change_summary(self, original: str, revised: str) -> str:
        """
        Generate a brief textual summary of changes.

        Useful for quick overview before detailed analysis.
        """
        result = self.compare(original, revised)
        stats = result["stats"]

        total_changes = stats["insertions"] + stats["deletions"]
        if total_changes == 0:
            return "No changes detected between the two versions."

        summary_parts = []
        if stats["deletions"] > 0:
            summary_parts.append(f"{stats['deletions']} deletion(s)")
        if stats["insertions"] > 0:
            summary_parts.append(f"{stats['insertions']} insertion(s)")

        change_ratio = stats["changed_chars"] / max(1, stats["unchanged_chars"] + stats["changed_chars"])

        if change_ratio < 0.05:
            scope = "Minor changes"
        elif change_ratio < 0.20:
            scope = "Moderate changes"
        elif change_ratio < 0.50:
            scope = "Significant changes"
        else:
            scope = "Extensive changes"

        return f"{scope}: {' and '.join(summary_parts)} detected."

class NDATriageService:
    """Rapid NDA triage screening service."""

    def __init__(self):
        self.prompt_loader = PromptLoader()
        self.playbook_service = PlaybookService()

    def triage(
        self,
        document_text: str,
        triage_context: str = "",
        apply_playbook: bool = True,
        user_id: Optional[int] = None,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform rapid triage screening on an NDA document.

        Args:
            document_text: The full NDA document text
            triage_context: User-provided context for the triage
            apply_playbook: Whether to apply playbook rules
            user_id: User ID for playbook lookup
            model: Optional model override

        Returns:
            Dict with classification, confidence, findings, risk_factors, etc.
        """
        if not LLM_AVAILABLE:
            return self._fallback_triage(document_text)

        playbook_context = ""
        if apply_playbook and user_id:
            playbook_ctx = self.playbook_service.get_relevant_context(
                document_text,
                user_id=user_id,
                max_clauses=5,
                max_rules=10
            )
            if playbook_ctx.get("rules") or playbook_ctx.get("clauses"):
                playbook_context = f"""
Your organization's playbook contains the following relevant rules and clauses:

Rules:
{json.dumps(playbook_ctx.get('rules', []), indent=2)}

Preferred Clauses:
{json.dumps(playbook_ctx.get('clauses', []), indent=2)}

Consider these when evaluating the NDA.
"""

        prompt = self.prompt_loader.load(
            "triage_nda",
            document_text=document_text[:15000],                                  
            triage_context=triage_context or "No specific context provided",
            playbook_context=playbook_context or "No playbook configured"
        )

        try:
            client = get_llm_client()
            effective_model = get_chat_model(model)

            response = client.chat.completions.create(
                model=effective_model,
                messages=[
                    {"role": "system", "content": "You are an expert legal analyst specializing in NDA review. Respond only in valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,                                                 
                max_tokens=2000
            )

            content = response.choices[0].message.content
            result = parse_llm_json(content)

            if result:

                if hasattr(response, 'usage') and response.usage:
                    result['tokens_used'] = {
                        'prompt': response.usage.prompt_tokens,
                        'completion': response.usage.completion_tokens,
                        'total': response.usage.total_tokens
                    }
                return result

            return self._fallback_triage(document_text)

        except Exception as e:
            logger.error(f"NDA triage LLM error: {e}")
            return self._fallback_triage(document_text)

    def _fallback_triage(self, document_text: str) -> Dict[str, Any]:
        """Fallback triage when LLM is unavailable."""
        text_lower = document_text.lower()

        risk_factors = []

        if "perpetual" in text_lower or "indefinite" in text_lower:
            risk_factors.append("Perpetual or indefinite term detected")
        if "non-compete" in text_lower:
            risk_factors.append("Non-compete clause detected")
        if "liquidated damages" in text_lower:
            risk_factors.append("Liquidated damages clause detected")
        if "audit" in text_lower and "right" in text_lower:
            risk_factors.append("Audit rights detected")

        if len(risk_factors) >= 2:
            classification = "FULL_REVIEW"
        elif len(risk_factors) == 1:
            classification = "COUNSEL_REVIEW"
        else:
            classification = "STANDARD_APPROVAL"

        return {
            "classification": classification,
            "confidence": 0.5,                               
            "summary": "Automated triage (LLM unavailable)",
            "key_findings": [],
            "risk_factors": risk_factors,
            "recommended_actions": ["Manual review recommended - automated analysis limited"],
            "playbook_deviations": []
        }

def get_document_differ() -> Optional[DocumentDiffer]:
    """Get a DocumentDiffer instance if available."""
    if not DIFF_AVAILABLE:
        logger.warning(f"get_document_differ: DIFF_AVAILABLE={DIFF_AVAILABLE}")
        return None
    try:
        differ = DocumentDiffer()
        logger.info("DocumentDiffer created successfully")
        return differ
    except Exception as e:
        logger.error(f"Failed to create DocumentDiffer: {e}")
        return None

