# lexwiki-compiler

Background sidecar that compiles each user's workspace into a LexWiki
markdown vault using a cheap LLM (default: `deepseek/deepseek-v4-flash` via
OpenRouter), then writes the compiled wiki + lint findings into the
`workspace_wikis` sqlite table.

The backend reads from that table to power the workspace **Knowledge** tab
(Clauses, Parties, Jurisdictions, Findings) and three agent retrieval tools
(`search_workspace`, `read_wiki_page`, `list_wiki_pages`).

## Layout

```
anylegal_oss/lexwiki_compiler/
├── runner.py             # CLI entry point: --loop / --once / --workspace <id>
├── poller.py             # finds workspaces needing recompile
├── compiler_job.py       # decrypt → scratch → compile → encrypt → store
├── lexwiki_runner.py     # wraps lexwiki.compile.compiler.WikiCompiler + WikiLinter
├── db.py                 # workspace_wikis schema + read/write helpers
├── config.py             # Config.from_env()
├── requirements.txt      # compiler-only deps (cryptography, dotenv)
├── Dockerfile
├── compose.snippet.yml
└── lexwiki_compiler.env.example
```

## How a compile happens

1. Poll loop calls `find_workspaces_needing_recompile(debounce_seconds=300)`.
   Returns workspaces where `workspaces.updated_at > workspace_wikis.compiled_at`
   AND no edits in the last 5 min.
2. For each candidate, `compiler_job.compile_workspace(wid, cfg)`:
   - Reads encrypted `workspace_documents`, decrypts via `decrypt_text`.
   - Hashes (path, modified_at, content_len) tuples; skips if unchanged.
   - Marks status `'compiling'`.
   - Materializes each compilable doc to `/app/scratch/<wid>/raw/<safe>.md`
     with YAML frontmatter (we already have extracted text, so we skip
     LexWiki's own extractor pipeline).
   - Runs `WikiCompiler(cfg).compile_all(full=False)` — incremental.
   - Runs `WikiLinter(cfg).lint_all()`.
   - Walks `/app/scratch/<wid>/wiki/` and assembles a `wiki_data` dict
     (pages + indexes + findings).
   - Encrypts `wiki_data` and upserts via `update_workspace_wiki()`.
   - Wipes scratch — never leaves decrypted source docs on disk.

Workspaces with zero compilable docs (only `Skills/`, `Templates/`,
`Playbook/`, `anylegal.md`) are marked `ready` with an empty wiki so the UI
shows an empty state rather than perpetual `pending`.

## How it ships

The lexwiki-compiler is one of the four services in the top-level
`docker-compose.yml`. `docker compose up` builds it from the backend
Dockerfile, mounts the same `./data/` volume the backend writes to, and
runs `python -m anylegal_oss.lexwiki_compiler.runner --loop`. No separate
build step.

To disable wiki compilation (e.g. on a low-RAM host), comment the
`lexwiki-compiler` service out of `docker-compose.yml`. The rest of the
app continues to work — readers of the `workspace_wikis` table just see
no compiled wiki.

## Manual debug — single workspace

When you want to compile one workspace without waiting for the poller's
debounce window:

```bash
docker compose exec lexwiki-compiler \
    python -m anylegal_oss.lexwiki_compiler.runner --once --workspace <wid>
```

Then inspect from the host:

```bash
sqlite3 data/anylegal_oss.db \
    "SELECT workspace_id, compile_status, source_doc_count, compile_error
     FROM workspace_wikis;"
```

(Replace `data/anylegal_oss.db` with whatever you set `DATABASE_PATH` to
in `.env`.)

## Heartbeat

The runner writes `/app/state/last_run.json` after every pass, with shape:

```json
{"ts": 1714305000.0, "candidates": 3, "ok": 3, "err": 0}
```

The host can probe this file's mtime to alert on stuck loops.
