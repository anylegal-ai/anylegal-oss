"""LexWiki compiler sidecar — builds per-workspace markdown knowledge bases.

Polls the workspaces table for changes, compiles each touched workspace's
documents into a LexWiki vault using a cheap LLM (deepseek/deepseek-v4-flash
via OpenRouter), then writes the compiled wiki + lint findings into the
workspace_wikis table.

Run as `python -m anylegal_oss.lexwiki_compiler.runner --loop` inside the
lexwiki-compiler container, or `--once --workspace <id>` for ad-hoc compiles.
"""
