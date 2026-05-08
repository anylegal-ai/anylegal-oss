"""Thin wrapper around LexWiki's compile + lint pipeline.

Isolates `from lexwiki.*` imports so the rest of the compiler package
can be imported even if LexWiki itself isn't installed (e.g. local dev
without the vendored submodule resolved). The runtime container has
LexWiki installed via the Dockerfile.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

def build_lexwiki_config(
    workspace_root: Path,
    *,
    model: str,
    base_url: str,
    api_key_env: str = "OPENROUTER_API_KEY",
    provider: str = "openrouter",
):
    """Construct a LexWikiConfig pointing at a per-workspace scratch dir."""
    from lexwiki.config import LexWikiConfig, LLMConfig, CompileConfig  # noqa: WPS433

    return LexWikiConfig(
        project_name=f"workspace-{workspace_root.name}",
        vault_dir=workspace_root,
        raw_dir=workspace_root / "raw",
        wiki_dir=workspace_root / "wiki",
        llm=LLMConfig(
            provider=provider,
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
        ),
        compile=CompileConfig(rebuild_indexes_on_compile=True),
    )

def compile_vault(workspace_root: Path, *, model: str, base_url: str) -> Dict[str, Any]:
    """Run WikiCompiler.compile_all on a workspace's scratch vault.

    Assumes raw documents have already been written to `workspace_root/raw/`
    by the caller. Returns the CompileStats from LexWiki as a dict, which
    callers may log or include in cost telemetry.
    """
    from lexwiki.compile.compiler import WikiCompiler  # noqa: WPS433

    cfg = build_lexwiki_config(workspace_root, model=model, base_url=base_url)
    compiler = WikiCompiler(cfg)
    stats = compiler.compile_all(full=False)
    return asdict(stats) if hasattr(stats, '__dataclass_fields__') else dict(stats or {})

def compile_vault_per_doc(
    workspace_root: Path,
    *,
    model: str,
    base_url: str,
    raw_stem_to_source: Dict[str, str],
) -> Dict[str, Any]:
    """Per-file compile loop that captures source_path -> slug mappings.

    Replaces compile_all's loop so we can attribute each compiled page back
    to its workspace source path (lexwiki's `source_raw` frontmatter field
    is only emitted when the LLM omits its own frontmatter, so we can't rely
    on it). For each raw .md in `raw_dir`:

      - If a fresh marker exists (caller pre-marked it for skip via the
        rehydration path), skip exactly as compile_all would.
      - Else, run WikiCompiler.compile_file and capture the produced slug.

    Then runs the standard index rebuild + backlinks pass that compile_all
    would have run after its loop.

    Returns:
        {
            "stats": {pages_created, indexes_rebuilt, backlinks_inserted},
            "source_to_slug": {workspace_path: "<category>/<slug>"},
        }
    """
    from lexwiki.compile.compiler import WikiCompiler  # noqa: WPS433
    from lexwiki.compile.backlinker import insert_backlinks  # noqa: WPS433

    cfg = build_lexwiki_config(workspace_root, model=model, base_url=base_url)
    compiler = WikiCompiler(cfg)
    raw_dir = cfg.raw_dir
    wiki_dir = cfg.wiki_dir

    pages_created = 0
    source_to_slug: Dict[str, str] = {}

    for raw_path in sorted(raw_dir.glob("*.md")):
        marker = raw_dir / ".compiled" / f"{raw_path.stem}.marker"
        if marker.exists() and marker.stat().st_mtime >= raw_path.stat().st_mtime:
            continue

        out_paths = compiler.compile_file(raw_path)
        pages_created += len(out_paths)

        source_path = raw_stem_to_source.get(raw_path.stem)
        if source_path and out_paths:
            slug = out_paths[0].relative_to(wiki_dir).with_suffix('').as_posix()
            source_to_slug[source_path] = slug

    indexes_rebuilt = 0
    if cfg.compile.rebuild_indexes_on_compile:
        idx_paths = compiler.rebuild_indexes()
        indexes_rebuilt = len(idx_paths)

    bl_count = insert_backlinks(wiki_dir)

    return {
        "stats": {
            "pages_created": pages_created,
            "indexes_rebuilt": indexes_rebuilt,
            "backlinks_inserted": bl_count,
        },
        "source_to_slug": source_to_slug,
    }

def lint_vault(workspace_root: Path, *, model: str, base_url: str) -> List[Dict[str, Any]]:
    """Run WikiLinter.lint_all and return findings as plain dicts.

    Each finding has the LintIssue shape:
        {severity, category, file, line, message, suggestion}
    """
    from lexwiki.lint.linter import WikiLinter  # noqa: WPS433

    cfg = build_lexwiki_config(workspace_root, model=model, base_url=base_url)
    linter = WikiLinter(cfg)
    issues = linter.lint_all()
    out: List[Dict[str, Any]] = []
    for issue in issues:
        if hasattr(issue, '__dataclass_fields__'):
            out.append(asdict(issue))
        elif isinstance(issue, dict):
            out.append(issue)
        else:
            logger.warning(f"Unexpected lint issue type: {type(issue)}")
    return out

def parse_yaml_frontmatter(text: str) -> tuple[Dict[str, Any], str]:
    """Split a markdown file's leading YAML frontmatter from its body.

    Handles three frontmatter shapes the LLM may emit:
      1. `---\\n...\\n---\\n`     — canonical YAML frontmatter
      2. ` ```yaml\\n...\\n``` `  — fenced YAML block at start (no `---`)
      3. bare `key: value` lines before the first markdown heading
         (less common but happens when the LLM forgets the wrapping)

    Returns ({} , text) if no frontmatter present. Tolerant of missing
    PyYAML (returns raw frontmatter as a single 'raw' key) so the compiler
    container doesn't strictly require pyyaml at runtime.
    """
    import re
    if not text:
        return {}, text

    if text.startswith('---\n'):
        end = text.find('\n---\n', 4)
        if end == -1:
            return {}, text
        fm_block = text[4:end]
        body = text[end + 5:]
        return _parse_yaml_block(fm_block), body

    fence_match = re.match(r'^```(?:yaml|yml|json)?\s*\n([\s\S]*?)\n```\s*\n*', text)
    if fence_match:
        fm_block = fence_match.group(1)
        body = text[fence_match.end():]
        return _parse_yaml_block(fm_block), body

    lines = text.split('\n')
    heading_idx = -1
    for i, line in enumerate(lines):
        if re.match(r'^#{1,6}\s', line):
            heading_idx = i
            break
    if heading_idx > 0:
        preamble_lines = lines[:heading_idx]

        all_yamlish = True
        yaml_content_lines: list[str] = []
        for line in preamble_lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == '```' or re.match(r'^```(?:yaml|yml|json)?$', stripped):
                continue
            if (
                re.match(r'^[A-Za-z_][A-Za-z0-9_-]*\s*:', line)
                or re.match(r'^\s+', line)                         
                or re.match(r'^\s*[-*]\s', line)             
            ):
                yaml_content_lines.append(line)
                continue
            all_yamlish = False
            break
        if all_yamlish and yaml_content_lines:
            fm_block = '\n'.join(yaml_content_lines).strip()
            body = '\n'.join(lines[heading_idx:])
            if len(body.strip()) > 50:
                parsed = _parse_yaml_block(fm_block)
                if parsed:
                    return parsed, body

    return {}, text

def _parse_yaml_block(fm_block: str) -> Dict[str, Any]:
    """Parse a YAML block, returning {} on failure rather than raising."""
    try:
        import yaml  # noqa: WPS433
        parsed = yaml.safe_load(fm_block) or {}
        if not isinstance(parsed, dict):
            return {"raw": fm_block}
        return parsed
    except ImportError:
        return {"raw": fm_block}
    except Exception as e:
        logger.warning(f"Failed to parse YAML frontmatter: {e}")
        return {"raw": fm_block}

INDEX_FILES = (
    "_index.md",
    "_by_type.md",
    "_by_jurisdiction.md",
    "_by_party.md",
    "_clause_library.md",
    "_precedent_map.md",
)

PAGE_SUBDIRS = ("contracts", "statutes", "cases", "memos", "topics")

def read_compiled_vault(workspace_root: Path) -> Dict[str, Any]:
    """Walk the compiled wiki dir and assemble the wiki_data payload.

    Output shape (consumed by the API and agent tools):
        {
            "pages": {
                "<category>/<slug>": {
                    "category": "contracts" | "statutes" | "cases" | "memos" | "topics",
                    "frontmatter": {...},
                    "compiled_body": "<markdown body — system-managed, rewritten on every compile>",
                    "annotations": [
                        # appended by the agent via append_wiki_note;
                        # carried forward across compiles by compiler_job.
                        {"author": "ai" | "user", "ts": "<iso>", "text": "..."}
                    ],
                }
            },
            "indexes": {
                "<index_name>": "<raw markdown>",
            },
        }
    """
    wiki_dir = workspace_root / "wiki"

    out: Dict[str, Any] = {
        "pages": {},
        "indexes": {},
        "workspace_notes": {"annotations": []},
    }

    if not wiki_dir.exists():
        logger.warning(f"Wiki dir does not exist: {wiki_dir}")
        return out

    for idx_name in INDEX_FILES:
        idx_path = wiki_dir / idx_name
        if idx_path.exists():
            try:
                content = idx_path.read_text(encoding='utf-8')
                key = idx_name.removesuffix('.md').lstrip('_')                                            
                out["indexes"][key] = content
            except Exception as e:
                logger.warning(f"Failed to read {idx_path}: {e}")

    for subdir in PAGE_SUBDIRS:
        sub_path = wiki_dir / subdir
        if not sub_path.exists():
            continue
        for md_file in sub_path.glob('*.md'):
            try:
                raw = md_file.read_text(encoding='utf-8')
                fm, body = parse_yaml_frontmatter(raw)
                slug = f"{subdir}/{md_file.stem}"
                out["pages"][slug] = {
                    "category": subdir,
                    "frontmatter": fm,
                    "compiled_body": body,
                    "annotations": [],                                            

                }
            except Exception as e:
                logger.warning(f"Failed to read page {md_file}: {e}")

    return out
