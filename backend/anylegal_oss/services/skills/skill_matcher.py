"""
Skill matcher — determines which skill(s) match a given user intent.
Enables automatic skill activation based on user request.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class SkillMatch:
    """Result of skill matching"""
    skill_name: str
    skill_path: str
    confidence: float             
    matched_patterns: List[str] = field(default_factory=list)
    description: Optional[str] = None

class SkillMatcher:
    """
    Matches user intents to skills using pattern recognition.
    Uses intent keywords, regex patterns, and embeddings (deferred).
    """

    def __init__(self):
        self.skills = {}                            
        self.patterns = []                                               
        logger.info("SkillMatcher initialized")

    def register_skill(
        self,
        skill_name: str,
        skill_path: str,
        description: str,
        intents: List[str],
        regex_patterns: Optional[List[str]] = None,
    ):
        """
        Register a skill for matching.

        Args:
            skill_name: Name of the skill (e.g., "contract_review")
            skill_path: Path to skill file/directory
            description: Human-readable description
            intents: List of intent keywords/phrases
            regex_patterns: Optional regex patterns for matching
        """
        self.skills[skill_name] = {
            "path": skill_path,
            "description": description,
            "intents": [i.lower() for i in intents],
        }

        for intent in intents:
            self.patterns.append((
                intent.lower(),
                skill_name,
                "keyword"
            ))

        if regex_patterns:
            for pattern in regex_patterns:
                self.patterns.append((
                    pattern,
                    skill_name,
                    "regex"
                ))

        logger.info(f"Registered skill: {skill_name} with {len(intents)} intents")

    def match(
        self,
        user_message: str,
        threshold: float = 0.3,
    ) -> List[SkillMatch]:
        """
        Match a user message to skills.

        Args:
            user_message: The user's input message
            threshold: Minimum confidence to include (0.0 - 1.0)

        Returns:
            List of SkillMatch sorted by confidence
        """
        message_lower = user_message.lower()
        matches = {}

        for pattern, skill_name, pattern_type in self.patterns:
            if pattern_type == "keyword":
                if pattern in message_lower:
                    confidence = len(pattern) / len(message_lower)               
                    if skill_name not in matches or confidence > matches[skill_name].confidence:
                        matches[skill_name] = SkillMatch(
                            skill_name=skill_name,
                            skill_path=self.skills[skill_name]["path"],
                            confidence=min(confidence * 2, 1.0),         
                            matched_patterns=[pattern],
                            description=self.skills[skill_name]["description"],
                        )

            elif pattern_type == "regex":
                try:
                    if re.search(pattern, user_message, re.IGNORECASE):
                        confidence = 0.7                   
                        if skill_name not in matches or confidence > matches[skill_name].confidence:
                            matches[skill_name] = SkillMatch(
                                skill_name=skill_name,
                                skill_path=self.skills[skill_name]["path"],
                                confidence=confidence,
                                matched_patterns=[pattern],
                                description=self.skills[skill_name]["description"],
                            )
                except re.error:
                    logger.warning(f"Invalid regex pattern: {pattern}")

        results = [m for m in matches.values() if m.confidence >= threshold]
        results.sort(key=lambda x: x.confidence, reverse=True)

        return results

    def match_all(
        self,
        user_message: str,
        max_results: int = 3,
    ) -> List[SkillMatch]:
        """
        Match and return top skills.

        Args:
            user_message: User's message
            max_results: Maximum number of results

        Returns:
            Top N skill matches
        """
        matches = self.match(user_message)
        return matches[:max_results]

    def get_skill_info(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """Get registered skill info"""
        return self.skills.get(skill_name)

    def list_skills(self) -> List[Dict[str, Any]]:
        """List all registered skills"""
        return [
            {
                "name": name,
                "path": info["path"],
                "description": info["description"],
                "intents": info["intents"],
            }
            for name, info in self.skills.items()
        ]

skill_matcher = SkillMatcher()

def get_skill_matcher() -> SkillMatcher:
    """Get the global skill matcher"""
    return skill_matcher

def register_builtin_skills():
    """
    Register built-in skills from the workspace/skills directory.
    Auto-discovers skills and their intents.
    """
    import os
    from anylegal_oss.workspace.skills.skill_loader import create_skill_loader

    try:

        skills_dir = os.path.join(os.path.dirname(__file__), "../../workspace/skills")
        if not os.path.exists(skills_dir):
            logger.warning(f"Skills directory not found: {skills_dir}")
            return

        loader = create_skill_loader(skills_dir)
        discovered = loader.discover_skills()

        for skill in discovered:

            skill_path = os.path.join(skills_dir, skill.name, "SKILL.md")

            intents = [skill.name.lower()]
            if skill.description:

                words = skill.description.lower().split()
                intents.extend(words[:5])                            

            register_skill(
                skill_name=skill.name,
                skill_path=skill_path,
                description=skill.description or skill.name,
                intents=list(set(intents)),
            )

        logger.info(f"Auto-registered {len(discovered)} built-in skills")

    except Exception as e:
        logger.error(f"Failed to register built-in skills: {e}")

def register_skill(
    skill_name: str,
    skill_path: str,
    description: str,
    intents: List[str],
    regex_patterns: Optional[List[str]] = None,
):
    """Convenience function to register a skill"""
    skill_matcher.register_skill(
        skill_name=skill_name,
        skill_path=skill_path,
        description=description,
        intents=intents,
        regex_patterns=regex_patterns,
    )

try:
    register_builtin_skills()
except Exception as e:
    logger.warning(f"Built-in skill registration failed: {e}")