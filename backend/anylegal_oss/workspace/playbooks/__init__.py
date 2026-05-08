"""
Playbook templates and utilities for the document editor.

This package contains default playbook templates that define standard positions
for common contract clauses. These templates can be used as starting points for
organizations to customize their own playbooks.

Key Components:
- PlaybookLoader: Load and manage playbooks from markdown files
- Playbook: Parsed playbook with metadata and clauses
- PlaybookClause: Individual clause position
"""

from .playbook_loader import (
    PlaybookLoader,
    Playbook,
    PlaybookClause,
    PlaybookMetadata,
    get_playbook_loader,
    load_user_playbook,
)

__all__ = [
    "PlaybookLoader",
    "Playbook",
    "PlaybookClause",
    "PlaybookMetadata",
    "get_playbook_loader",
    "load_user_playbook",
]
