"""
SkillLoader - Load and manage SKILL.md files

Provides skill discovery, loading, and eligibility checking.
Skills are defined in SKILL.md files with YAML frontmatter.

Compatible with OpenSkills/Anthropic models SKILL.md format.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

@dataclass
class SkillRequirements:
    """Requirements for a skill to be eligible."""
    tools: List[str] = field(default_factory=list)
    config: List[str] = field(default_factory=list)                     
    binaries: List[str] = field(default_factory=list)                      

@dataclass
class SkillMetadata:
    """Metadata parsed from SKILL.md frontmatter."""
    name: str
    emoji: str = ""
    description: str = ""
    requires: SkillRequirements = field(default_factory=SkillRequirements)
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)

@dataclass
class Skill:
    """A loaded skill with metadata and content."""
    metadata: SkillMetadata
    content: str                                               
    path: Path

    when_to_use: str = ""
    process: str = ""
    output_format: str = ""
    guidelines: str = ""

class SkillLoader:
    """
    Loads and manages SKILL.md files.

    Supports:
    - Discovering skills from multiple directories
    - Parsing YAML frontmatter for metadata
    - Progressive disclosure (L1, L2, L3 context levels)
    - Eligibility checking based on requirements
    """

    def __init__(
        self,
        skills_dirs: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the skill loader.

        Args:
            skills_dirs: List of directories to search for skills
            config: Configuration dict for eligibility checks
        """
        self.skills_dirs = skills_dirs or []
        self.config = config or {}
        self._cache: Dict[str, Skill] = {}
        self._metadata_cache: Dict[str, SkillMetadata] = {}

    def add_skills_dir(self, path: str) -> None:
        """Add a directory to search for skills."""
        if path not in self.skills_dirs:
            self.skills_dirs.append(path)

    def discover_skills(self, check_eligibility: bool = False) -> List[SkillMetadata]:
        """
        Discover all available skills.

        Args:
            check_eligibility: If True, only return eligible skills

        Returns:
            List of SkillMetadata for discovered skills
        """
        skills = []

        for skills_dir in self.skills_dirs:
            dir_path = Path(skills_dir)
            if not dir_path.exists():
                logger.debug(f"Skills directory not found: {skills_dir}")
                continue

            for skill_path in dir_path.glob("*/SKILL.md"):
                try:
                    metadata = self._parse_metadata(skill_path)
                    if metadata:
                        if check_eligibility and not self.is_eligible(metadata):
                            logger.debug(f"Skill not eligible: {metadata.name}")
                            continue
                        skills.append(metadata)
                        self._metadata_cache[metadata.name] = metadata
                except Exception as e:
                    logger.error(f"Error parsing skill {skill_path}: {e}")

        return skills

    def load_skill(self, name: str, level: int = 2) -> Optional[Skill]:
        """
        Load a skill by name.

        Args:
            name: Skill name (e.g., 'contract-review')
            level: Context level (1=minimal, 2=standard, 3=full)

        Returns:
            Loaded Skill or None if not found
        """
        # Defense-in-depth: skill names are admin-controlled today, but reject
        # any traversal-shaped string so a future caller can't turn this into
        # an arbitrary-file read.
        if not name or ".." in name or name.startswith(("/", "\\")) or "/" in name or "\\" in name:
            logger.warning(f"Rejecting skill name with path components: {name!r}")
            return None

        cache_key = f"{name}:{level}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        for skills_dir in self.skills_dirs:
            skill_path = Path(skills_dir) / name / "SKILL.md"
            if skill_path.exists():
                skill = self._load_skill_file(skill_path, level)
                if skill:
                    self._cache[cache_key] = skill
                    return skill

        logger.warning(f"Skill not found: {name}")
        return None

    def get_skill_content(self, name: str, level: int = 2) -> Optional[str]:
        """
        Get skill content at specified disclosure level.

        Level 1: Just the description
        Level 2: Description + When to Use + Process
        Level 3: Full content including guidelines
        """
        skill = self.load_skill(name, level)
        if not skill:
            return None

        if level == 1:
            return f"# {skill.metadata.name}\n\n{skill.metadata.description}"
        elif level == 2:
            parts = [
                f"# {skill.metadata.name}",
                f"\n{skill.metadata.description}",
            ]
            if skill.when_to_use:
                parts.append(f"\n## When to Use\n{skill.when_to_use}")
            if skill.process:
                parts.append(f"\n## Process\n{skill.process}")
            return "\n".join(parts)
        else:           
            return skill.content

    def is_eligible(self, skill_or_name) -> bool:
        """
        Check if a skill's requirements are met.

        Checks:
        - Required config/env vars
        - Required binaries
        - Required tools are available
        """
        if isinstance(skill_or_name, str):
            metadata = self._metadata_cache.get(skill_or_name)
            if not metadata:

                for skills_dir in self.skills_dirs:
                    skill_path = Path(skills_dir) / skill_or_name / "SKILL.md"
                    if skill_path.exists():
                        metadata = self._parse_metadata(skill_path)
                        break
            if not metadata:
                return False
        else:
            metadata = skill_or_name

        requirements = metadata.requires

        for config_key in requirements.config:
            if config_key not in self.config and not os.getenv(config_key):
                logger.debug(f"Missing config: {config_key}")
                return False

        import shutil
        for binary in requirements.binaries:
            if not shutil.which(binary):
                logger.debug(f"Missing binary: {binary}")
                return False

        return True

    def _parse_metadata(self, skill_path: Path) -> Optional[SkillMetadata]:
        """Parse metadata from SKILL.md frontmatter."""
        try:
            content = skill_path.read_text(encoding='utf-8')

            frontmatter_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not frontmatter_match:
                logger.warning(f"No frontmatter in {skill_path}")
                return None

            frontmatter = yaml.safe_load(frontmatter_match.group(1))
            if not frontmatter:
                return None

            if 'allowed-tools' in frontmatter and 'requires' not in frontmatter:
                tools = frontmatter['allowed-tools']
                if isinstance(tools, str):
                    tools = [t.strip() for t in tools.split(',') if t.strip()]
                frontmatter['requires'] = {'tools': tools}

            requires_data = frontmatter.get('requires', {})
            requirements = SkillRequirements(
                tools=requires_data.get('tools', []) if isinstance(requires_data, dict) else [],
                config=requires_data.get('config', []) if isinstance(requires_data, dict) else [],
                binaries=requires_data.get('binaries', []) if isinstance(requires_data, dict) else [],
            )

            return SkillMetadata(
                name=frontmatter.get('name', skill_path.parent.name),
                emoji=frontmatter.get('emoji', ''),
                description=frontmatter.get('description', ''),
                requires=requirements,
                version=frontmatter.get('version', '1.0.0'),
                author=frontmatter.get('author', ''),
                tags=frontmatter.get('tags', []),
            )

        except Exception as e:
            logger.error(f"Error parsing metadata from {skill_path}: {e}")
            return None

    def _load_skill_file(self, skill_path: Path, level: int) -> Optional[Skill]:
        """Load a skill from file."""
        try:
            content = skill_path.read_text(encoding='utf-8')

            metadata = self._parse_metadata(skill_path)
            if not metadata:
                return None

            content_without_frontmatter = re.sub(
                r'^---\s*\n.*?\n---\s*\n',
                '',
                content,
                flags=re.DOTALL
            )

            skill = Skill(
                metadata=metadata,
                content=content_without_frontmatter,
                path=skill_path,
            )

            skill.when_to_use = self._extract_section(content_without_frontmatter, "When to Use")
            skill.process = self._extract_section(content_without_frontmatter, "Process")
            skill.output_format = self._extract_section(content_without_frontmatter, "Output Format")
            skill.guidelines = self._extract_section(content_without_frontmatter, "Guidelines")

            return skill

        except Exception as e:
            logger.error(f"Error loading skill from {skill_path}: {e}")
            return None

    def _extract_section(self, content: str, section_name: str) -> str:
        """Extract a section from markdown content."""
        pattern = rf'##\s+{re.escape(section_name)}\s*\n(.*?)(?=\n##\s|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def get_tools_for_skill(self, name: str) -> List[str]:
        """Get the list of tools required by a skill."""
        metadata = self._metadata_cache.get(name)
        if not metadata:
            skill = self.load_skill(name)
            if skill:
                metadata = skill.metadata

        return metadata.requires.tools if metadata else []

def create_skill_loader(skills_dir: str = None, config: dict = None) -> SkillLoader:
    """Create a SkillLoader with default settings."""
    loader = SkillLoader(config=config)

    if skills_dir:
        loader.add_skills_dir(skills_dir)
    else:

        default_dir = Path(__file__).parent
        loader.add_skills_dir(str(default_dir))

    return loader
