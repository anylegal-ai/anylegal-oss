"""
Skills module for the Document Editor.

This module contains agentic skills for contract review, redline generation,
and legal research. Skills are defined as SKILL.md files in subdirectories
following the OpenSkills/Anthropic models format.
"""

from pathlib import Path

SKILLS_DIR = Path(__file__).parent

AVAILABLE_SKILLS = [
    "contract-review",
    "redline",
    "research"
]

__all__ = ["SKILLS_DIR", "AVAILABLE_SKILLS"]
