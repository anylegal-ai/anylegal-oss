"""
PlaybookLoader - Markdown-based Playbook Management

This module provides a file-first approach to playbook management,
loading from markdown files with optional DB fallback.

Copyright 2026 AnyLegal
Licensed under the Apache License, Version 2.0
"""

import os
import re
import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PLAYBOOKS_DIR = Path(__file__).parent
DEFAULT_PLAYBOOK_PATH = PLAYBOOKS_DIR / "default-commercial.md"
USER_PLAYBOOKS_DIR = PLAYBOOKS_DIR / "users"

@dataclass
class PlaybookMetadata:
    """Metadata from playbook YAML frontmatter."""
    name: str = "Untitled Playbook"
    version: str = "1.0"
    author: Optional[str] = None
    organization: Optional[str] = None
    jurisdiction: str = "GENERAL"
    contract_types: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass 
class PlaybookClause:
    """A clause position from the playbook."""
    clause_type: str
    title: str
    acceptable: List[str] = field(default_factory=list)
    requires_review: List[str] = field(default_factory=list)
    unacceptable: List[str] = field(default_factory=list)
    fallback_text: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class Playbook:
    """Parsed playbook with metadata and clauses."""
    metadata: PlaybookMetadata
    clauses: Dict[str, PlaybookClause]
    raw_content: str
    source: str                           

    def get_clause(self, clause_type: str) -> Optional[PlaybookClause]:
        """Get a clause by type (case-insensitive, underscore-tolerant)."""
        normalized = clause_type.lower().replace('_', ' ').replace('-', ' ')
        for key, clause in self.clauses.items():
            key_normalized = key.lower().replace('_', ' ').replace('-', ' ')
            if key_normalized == normalized:
                return clause
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "metadata": {
                "name": self.metadata.name,
                "version": self.metadata.version,
                "author": self.metadata.author,
                "organization": self.metadata.organization,
                "jurisdiction": self.metadata.jurisdiction,
                "contract_types": self.metadata.contract_types,
            },
            "clauses": {
                k: {
                    "clause_type": v.clause_type,
                    "title": v.title,
                    "acceptable": v.acceptable,
                    "requires_review": v.requires_review,
                    "unacceptable": v.unacceptable,
                    "fallback_text": v.fallback_text,
                }
                for k, v in self.clauses.items()
            },
            "source": self.source
        }

class PlaybookLoader:
    """
    Load and manage playbooks from markdown files.

    Priority order:
    1. User's markdown file (playbooks/users/{user_id}.md)
    2. Database clauses (via PlaybookService)
    3. Default playbook (playbooks/default-commercial.md)
    """

    def __init__(self, user_playbooks_dir: Optional[Path] = None):
        """
        Initialize the PlaybookLoader.

        Args:
            user_playbooks_dir: Directory for user playbooks (default: playbooks/users/)
        """
        self.user_playbooks_dir = user_playbooks_dir or USER_PLAYBOOKS_DIR
        self.user_playbooks_dir.mkdir(parents=True, exist_ok=True)

    def get_playbook_path(self, user_id: int) -> Path:
        """Get the path to a user's playbook file."""
        return self.user_playbooks_dir / f"{user_id}.md"

    def load_playbook(
        self,
        user_id: Optional[int] = None,
        fallback_to_db: bool = True,
        fallback_to_default: bool = True
    ) -> Optional[Playbook]:
        """
        Load a user's playbook with fallback chain.

        Args:
            user_id: User ID to load playbook for
            fallback_to_db: Whether to fallback to DB if no file
            fallback_to_default: Whether to fallback to default if no DB

        Returns:
            Parsed Playbook object or None
        """

        if user_id:
            user_path = self.get_playbook_path(user_id)
            if user_path.exists():
                try:
                    content = user_path.read_text(encoding="utf-8")
                    return self._parse_playbook(content, source="file")
                except Exception as e:
                    logger.warning(f"Error loading user playbook: {e}")

        if fallback_to_db and user_id:
            try:
                from ..services import PlaybookService
                from .. import db

                service = PlaybookService(user_id)
                clauses = service.get_clauses(limit=1000)

                if clauses:

                    return self._db_clauses_to_playbook(clauses, user_id)
            except Exception as e:
                logger.debug(f"DB playbook not available: {e}")

        if fallback_to_default:
            return self.load_default_playbook()

        return None

    def load_default_playbook(self) -> Optional[Playbook]:
        """Load the default commercial playbook."""
        if not DEFAULT_PLAYBOOK_PATH.exists():
            logger.warning("Default playbook not found")
            return None

        try:
            content = DEFAULT_PLAYBOOK_PATH.read_text(encoding="utf-8")
            return self._parse_playbook(content, source="default")
        except Exception as e:
            logger.error(f"Error loading default playbook: {e}")
            return None

    def save_playbook(self, user_id: int, content: str) -> bool:
        """
        Save a user's playbook markdown file.

        Args:
            user_id: User ID
            content: Markdown content to save

        Returns:
            True if saved successfully
        """
        try:
            path = self.get_playbook_path(user_id)

            content = self._update_timestamp(content)

            path.write_text(content, encoding="utf-8")
            logger.info(f"Saved playbook for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error saving playbook: {e}")
            return False

    def delete_playbook(self, user_id: int) -> bool:
        """Delete a user's playbook file."""
        try:
            path = self.get_playbook_path(user_id)
            if path.exists():
                path.unlink()
                logger.info(f"Deleted playbook for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting playbook: {e}")
            return False

    def export_db_to_markdown(self, user_id: int) -> Optional[str]:
        """
        Export a user's DB playbook clauses to markdown format.

        Args:
            user_id: User ID to export

        Returns:
            Markdown string or None
        """
        try:
            from ..services import PlaybookService

            service = PlaybookService(user_id)
            clauses = service.get_clauses(limit=1000)

            if not clauses:
                return None

            return self._clauses_to_markdown(clauses, user_id)
        except Exception as e:
            logger.error(f"Error exporting playbook: {e}")
            return None

    def _parse_playbook(self, content: str, source: str) -> Playbook:
        """Parse markdown content into a Playbook object."""

        metadata = PlaybookMetadata()
        body = content

        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if frontmatter_match:
            try:
                fm_data = yaml.safe_load(frontmatter_match.group(1))
                if fm_data:
                    metadata = PlaybookMetadata(
                        name=fm_data.get("name", "Untitled Playbook"),
                        version=fm_data.get("version", "1.0"),
                        author=fm_data.get("author"),
                        organization=fm_data.get("organization"),
                        jurisdiction=fm_data.get("jurisdiction", "GENERAL"),
                        contract_types=fm_data.get("contract_types", []),
                        created_at=fm_data.get("created_at"),
                        updated_at=fm_data.get("updated_at"),
                    )
            except yaml.YAMLError as e:
                logger.warning(f"Error parsing frontmatter: {e}")
            body = content[frontmatter_match.end():]

        clauses = self._parse_clauses(body)

        return Playbook(
            metadata=metadata,
            clauses=clauses,
            raw_content=content,
            source=source
        )

    def _parse_clauses(self, content: str) -> Dict[str, PlaybookClause]:
        """Parse clause sections from markdown body."""
        clauses = {}

        sections = re.split(r'\n(?=## )', content)

        for section in sections:
            if not section.strip():
                continue

            title_match = re.match(r'^## (.+)', section)
            if not title_match:
                continue

            title = title_match.group(1).strip()

            clause_type = title.lower().replace(' ', '_')

            acceptable = self._extract_list_section(section, "Acceptable")
            requires_review = self._extract_list_section(section, "Requires Review")
            unacceptable = self._extract_list_section(section, "Unacceptable")
            fallback = self._extract_text_section(section, "Fallback")
            notes = self._extract_text_section(section, "Notes")

            clauses[clause_type] = PlaybookClause(
                clause_type=clause_type,
                title=title,
                acceptable=acceptable,
                requires_review=requires_review,
                unacceptable=unacceptable,
                fallback_text=fallback,
                notes=notes
            )

        return clauses

    def _extract_list_section(self, content: str, section_name: str) -> List[str]:
        """Extract bullet points from a subsection."""
        pattern = rf'###\s*{section_name}\s*\n(.*?)(?=###|\Z)'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

        if not match:
            return []

        text = match.group(1)
        items = re.findall(r'[-•]\s*(.+)', text)
        return [item.strip() for item in items if item.strip()]

    def _extract_text_section(self, content: str, section_name: str) -> Optional[str]:
        """Extract text content from a subsection."""
        pattern = rf'###\s*{section_name}\s*\n(.*?)(?=###|\Z)'
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

        if not match:
            return None

        text = match.group(1).strip()

        text = re.sub(r'^[-•]\s*', '', text, flags=re.MULTILINE)
        return text if text else None

    def _db_clauses_to_playbook(self, clauses: List[Dict], user_id: int) -> Playbook:
        """Convert DB clauses to a Playbook object."""
        parsed_clauses = {}

        by_type: Dict[str, List[Dict]] = {}
        for clause in clauses:
            ct = clause.get("clause_type", "other")
            if ct not in by_type:
                by_type[ct] = []
            by_type[ct].append(clause)

        for clause_type, items in by_type.items():
            acceptable = []
            requires_review = []
            unacceptable = []
            fallback_text = None

            for item in items:
                position = item.get("position", "balanced")
                text = item.get("clause_text", "")
                title = item.get("title", "")

                entry = f"{title}: {text[:200]}..." if len(text) > 200 else f"{title}: {text}"

                if position in ("favorable", "acceptable"):
                    acceptable.append(entry)
                elif position in ("neutral", "balanced"):
                    requires_review.append(entry)
                elif position in ("unfavorable", "adverse"):
                    unacceptable.append(entry)

                if not fallback_text and position == "favorable":
                    fallback_text = text

            parsed_clauses[clause_type] = PlaybookClause(
                clause_type=clause_type,
                title=clause_type.replace("_", " ").title(),
                acceptable=acceptable,
                requires_review=requires_review,
                unacceptable=unacceptable,
                fallback_text=fallback_text
            )

        markdown = self._clauses_to_markdown(clauses, user_id)

        return Playbook(
            metadata=PlaybookMetadata(
                name=f"User {user_id} Playbook",
                version="1.0",
                created_at=datetime.now(timezone.utc).isoformat(),
            ),
            clauses=parsed_clauses,
            raw_content=markdown or "",
            source="db"
        )

    def _clauses_to_markdown(self, clauses: List[Dict], user_id: int) -> str:
        """Convert DB clauses to markdown format."""
        lines = [
            "---",
            f'name: "User {user_id} Playbook"',
            'version: "1.0"',
            f'exported_at: "{datetime.now(timezone.utc).isoformat()}"',
            "---",
            "",
            "# Playbook",
            "",
        ]

        by_type: Dict[str, List[Dict]] = {}
        for clause in clauses:
            ct = clause.get("clause_type", "other")
            if ct not in by_type:
                by_type[ct] = []
            by_type[ct].append(clause)

        for clause_type, items in by_type.items():
            title = clause_type.replace("_", " ").title()
            lines.append(f"## {title}")
            lines.append("")

            favorable = [c for c in items if c.get("position") in ("favorable", "acceptable")]
            neutral = [c for c in items if c.get("position") in ("neutral", "balanced")]
            adverse = [c for c in items if c.get("position") in ("unfavorable", "adverse")]

            if favorable:
                lines.append("### Acceptable")
                lines.append("")
                for c in favorable:
                    lines.append(f"- {c.get('title', 'Untitled')}: {c.get('clause_text', '')[:200]}")
                lines.append("")

            if neutral:
                lines.append("### Requires Review")
                lines.append("")
                for c in neutral:
                    lines.append(f"- {c.get('title', 'Untitled')}: {c.get('clause_text', '')[:200]}")
                lines.append("")

            if adverse:
                lines.append("### Unacceptable")
                lines.append("")
                for c in adverse:
                    lines.append(f"- {c.get('title', 'Untitled')}: {c.get('clause_text', '')[:200]}")
                lines.append("")

        return "\n".join(lines)

    def _update_timestamp(self, content: str) -> str:
        """Update the updated_at timestamp in frontmatter."""
        now = datetime.now(timezone.utc).isoformat()

        frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)

        if frontmatter_match:
            fm_text = frontmatter_match.group(1)

            if "updated_at:" in fm_text:
                fm_text = re.sub(r'updated_at:.*', f'updated_at: "{now}"', fm_text)
            else:
                fm_text += f'\nupdated_at: "{now}"'

            return f"---\n{fm_text}\n---\n" + content[frontmatter_match.end():]
        else:

            return f'---\nupdated_at: "{now}"\n---\n\n' + content

def get_playbook_loader() -> PlaybookLoader:
    """Get a PlaybookLoader instance."""
    return PlaybookLoader()

def load_user_playbook(user_id: int) -> Optional[Playbook]:
    """Convenience function to load a user's playbook."""
    return PlaybookLoader().load_playbook(user_id)
