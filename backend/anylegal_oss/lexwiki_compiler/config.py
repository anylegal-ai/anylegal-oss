"""LexWiki compiler configuration, loaded from environment.

Mirrors the dataclass-from-env pattern in observer/config.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"required env var not set: {name}")
    return v

def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    return int(v) if v else default

def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

@dataclass(frozen=True)
class Config:

    openrouter_api_key: str
    model: str
    base_url: str
    require_zdr: bool

    encryption_key: str

    db_path: Path
    scratch_dir: Path
    state_dir: Path

    poll_interval_seconds: int
    debounce_seconds: int
    max_workspaces_per_pass: int

    max_docs_per_workspace: int
    max_doc_chars: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            openrouter_api_key=_env("OPENROUTER_API_KEY", required=True) or "",

            model=_env("LEXWIKI_MODEL", "deepseek/deepseek-v3.2") or "deepseek/deepseek-v3.2",

            base_url=_env("LEXWIKI_BASE_URL", "https://openrouter.ai/api") or "https://openrouter.ai/api",
            require_zdr=_env_bool("OPENROUTER_ZDR", True),
            encryption_key=_env("ANYLEGAL_ENCRYPTION_KEY", default="") or "",
            db_path=Path(_env("LEXWIKI_COMPILER_DB_PATH", "./data/anylegal_oss.db") or ""),
            scratch_dir=Path(_env("LEXWIKI_COMPILER_SCRATCH_DIR", "/app/scratch") or ""),
            state_dir=Path(_env("LEXWIKI_COMPILER_STATE_DIR", "/app/state") or ""),
            poll_interval_seconds=_env_int("LEXWIKI_COMPILER_POLL_INTERVAL", 60),
            debounce_seconds=_env_int("LEXWIKI_COMPILER_DEBOUNCE_SECONDS", 300),
            max_workspaces_per_pass=_env_int("LEXWIKI_COMPILER_MAX_PER_PASS", 5),
            max_docs_per_workspace=_env_int("LEXWIKI_COMPILER_MAX_DOCS", 200),
            max_doc_chars=_env_int("LEXWIKI_COMPILER_MAX_DOC_CHARS", 200_000),
        )
