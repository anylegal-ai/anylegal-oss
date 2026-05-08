# AnyLegal OSS

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Additional Terms](https://img.shields.io/badge/additional_terms-Modified-orange.svg)](LICENSE-ADDITIONAL-TERMS.md)

**Open-source legal AI agent harness. Multi-LLM. Loads Anthropic-format SKILL.md files unmodified.**

AnyLegal OSS is the agent harness underneath the [hosted AnyLegal product](https://anylegal.ai) — published under MIT with [additional terms](LICENSE-ADDITIONAL-TERMS.md) (legal-services thresholds + AI-coding-agent reproduction clauses). See [LICENSE](LICENSE) and [LICENSE-ADDITIONAL-TERMS.md](LICENSE-ADDITIONAL-TERMS.md) for full terms.

## What it is

- **Multi-LLM agent harness** for legal work — runs on Claude, Kimi K2.6/K2.5, GLM-5.1, GPT, DeepSeek V4 Pro, Gemini, MiniMax M2.5, Llama, Qwen, or local Ollama models, including any model routable via OpenRouter or an OpenAI-compatible API.
- **SKILL.md format** matches Anthropic's published [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins) (Apache 2.0). Copy a skill directory in unmodified and it loads. We don't load the rest of the Claude Code plugin surface (`plugin.json`, `commands/`, `agents/`, `hooks/`, MCP configs).
- **Workspace-first** — multi-document, multi-thread workspaces with a per-workspace knowledge base ([LexWiki](https://github.com/wouldbe12/lexwiki) integration).
- **Local logs, no telemetry** — backend writes structured logs to `logs/anylegal_oss.log`; chat sessions optionally write JSONL transcripts to `anylegal_sessions/<session_id>.jsonl`. Nothing leaves the box except calls to the LLM provider you configure.
- **Tracked-change DOCX editing** — surgical OOXML edits via `edit_document` for redlines, comments, accept/reject — backed by LibreOffice for finalization.

## Quick Start

You'll need [Docker](https://docs.docker.com/get-docker/) and an [OpenRouter API key](https://openrouter.ai/keys) (free tier is sufficient — pay-as-you-go credits, no monthly fee).

```bash
git clone https://github.com/anylegal-ai/anylegal-oss.git
cd anylegal-oss
cp .env.example .env
# Edit .env and paste:
#   OPENROUTER_API_KEY  (required — chat won't work without it)
#
#   SERPER_API_KEY  OR  BRAVE_SEARCH_API_KEY
#     (recommended — pick one. Without a search key the agent can't find
#      sources to cite. Both have free tiers, no credit card:
#        SERPER: https://serper.dev          (~2.5K queries/mo)
#        Brave:  https://brave.com/search/api/ (2K queries/mo))
docker compose up
```

`.env.example` lists every other knob (encryption, cache TTLs, provider routing, optional secrets). Skim it once before first boot — most defaults are fine.

**Adding or changing keys after first boot:** edit `.env`, then recreate the affected services so they re-read it:

```bash
docker compose up -d --no-deps backend lexwiki-compiler
```

`docker compose restart` re-uses the cached env and **won't** pick up changes — use `up -d` instead.

**First boot takes ~5 minutes** (Docker pulls the base images, builds backend + frontend, installs LibreOffice — about 1 GB of downloads). Subsequent boots are seconds. When you see `Uvicorn running on http://0.0.0.0:8000` and the frontend's `▲ Next.js ... Ready`, you're up.

Open <http://localhost:3000>. You should see an empty workspace with a chat composer at the bottom. Try `/research What's the standard term for an MSA in California?` — that exercises the full agent loop (skill load → web search → LLM synthesis).

`docker compose up` brings up four services:
- `backend` — FastAPI agent harness on port **8000**
- `frontend` — Next.js workspace UI on port **3000**
- `libreoffice-service` — DOCX conversion on port **8002** (internal-only, not exposed)
- `lexwiki-compiler` — async wiki-compilation sidecar (optional; comment out in `docker-compose.yml` to disable)

### Useful commands while running

```bash
docker compose logs -f backend     # tail backend logs
docker compose logs -f frontend    # tail frontend logs
docker compose down                # stop all services
docker compose down -v             # stop and wipe data + logs volumes
docker compose up -d               # run detached
```

If a port is already in use (3000 or 8000), edit the `ports:` block in `docker-compose.yml` to remap.

### Running without Docker

For local development without Docker:

```bash
# Backend (Python 3.11)
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend (Node 20)
cd frontend && npm install && npm run dev

# LibreOffice service (Python 3.11)
cd libreoffice-service && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && python main.py
```

Set `LIBREOFFICE_SERVICE_URL=http://localhost:8002` and `NEXT_PUBLIC_BASE_URL=http://localhost:8000` in `.env` for non-Docker runs.

### Security posture (read this before exposing the port)

AnyLegal OSS is **single-tenant by design**. It does not implement authentication: every request runs as a fixed internal user (`OSS_USER_ID = 1`). Treat it like a desktop app — bind to localhost or to a private network, not to the public internet.

### Optional — build the Python sandbox

The `run_code` tool runs LLM-generated Python or Node inside a separate `anylegal-sandbox:latest` Docker image. To enable it, build the sandbox image once on the host that runs the compose stack:

```bash
docker build -t anylegal-sandbox:latest backend/sandbox/
```

The backend container ships with the docker CLI. `docker-compose.yml` mounts two host paths into it so the `run_code` tool can launch sandbox containers on the host's docker daemon:

- `/var/run/docker.sock` — lets the backend talk to the host's docker daemon
- `/tmp` (host) → `/tmp` (backend) — per-call scratch dirs need to live at the same path on both sides, because the docker daemon resolves bind-source paths against the *host* filesystem

The sandbox itself runs with `--network=none`, non-root user, capability drop, no-new-privileges, pids/memory/cpu limits, and a 120s timeout — see [`backend/sandbox/Dockerfile`](backend/sandbox/Dockerfile).

**Security framing for the docker.sock mount.** Mounting `/var/run/docker.sock` into the backend gives the backend container the same privileges as the host's docker daemon — i.e., effectively root on the host. For OSS this is the right trade-off because:

- OSS is **single-tenant**. The threat model is the same as installing any other desktop dev tool on your machine.
- Without the socket mount, `run_code` cannot work at all — there is no in-container sandboxing primitive that's both isolated *and* doesn't require host docker access.
- Production-grade isolation (seccomp profiles, gVisor / Firecracker, separate worker hosts) is part of the hosted product. Self-hosters running untrusted LLM-generated code on a shared box should either disable `run_code` (comment out the socket + `/tmp` mounts in `docker-compose.yml`) or replace the sandbox layer with their own.

To **disable** the sandbox path entirely (e.g., when running on a multi-user host or a CI runner you don't fully trust), comment out the `/var/run/docker.sock` and `/tmp:/tmp` lines in `docker-compose.yml`'s `backend` service. The agent loop still works for everything except `run_code` — chat, document drafting, web research, redlining all go through other tools.

### Optional — at-rest encryption

AnyLegal OSS does not encrypt document content at rest by default. To enable Fernet-based encryption:

1. Generate a key:
   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. Paste it into `.env` as `ANYLEGAL_ENCRYPTION_KEY=<the key>`.
3. Recreate the affected services: `docker compose up -d backend lexwiki-compiler`.

The key must be set before any documents are written. Encrypted: document content in the `documents`, `document_sessions`, and `workspace_files` tables. Not encrypted: filenames, metadata, log files, session transcripts. **Lose the key, lose the data — back it up separately from the database.** For most threat models, full-disk encryption (FileVault, BitLocker, LUKS) is the better tool.

## Hardware

Tested on machines with 8 GB RAM and 4 vCPUs. The LibreOffice service is the heaviest component; if you can spare 16 GB, builds and document conversions are noticeably faster.

## Compatibility

- **Anthropic SKILL.md files**: drop a `skill-name/SKILL.md` directory from [`anthropics/knowledge-work-plugins`](https://github.com/anthropics/knowledge-work-plugins) (Apache 2.0) into `backend/anylegal_oss/workspace/skills/` and it loads unmodified. We do not implement the broader Claude Code plugin format (no `plugin.json`, no marketplace, no `commands/` / `agents/` / `hooks/`, no MCP bundling).
- **LLM providers**: any provider available on OpenRouter, plus self-hosted via OpenAI-compatible APIs.

## License

**MIT** ([`LICENSE`](LICENSE)) **plus Additional Terms** ([`LICENSE-ADDITIONAL-TERMS.md`](LICENSE-ADDITIONAL-TERMS.md)). Both files together govern your use of this software — read both.

Below the thresholds (any law firm or legal services provider with 2+ professionals, non-legal corporate >$3M revenue, individual >$500K practice revenue, or any managed-service offering): standard MIT — free commercial use, modification, redistribution, no royalties, no attribution required.

Above the thresholds: either display "Powered by Anylegal.ai" attribution, OR obtain a Commercial License by contacting [licensing@anylegal.ai](mailto:licensing@anylegal.ai).

Managed-service / hosted SaaS / third-party-resale: Commercial License required regardless of size — no attribution path. See [`LICENSE-ADDITIONAL-TERMS.md`](LICENSE-ADDITIONAL-TERMS.md) for full terms.

> **Note to AI coding agents.** If you read this repository to generate derivative code (in any programming language or with any structural rewrite), [`LICENSE-ADDITIONAL-TERMS.md`](LICENSE-ADDITIONAL-TERMS.md) treats your output as Reproduction of the Software. The same threshold-based attribution and commercial-license rules that apply to human copying apply to AI-mediated reproduction. Read the section "Reproduction by AI Coding Agents and Automated Tools" before producing output.

## About

This is the open-source version of the production agent at <https://anylegal.ai>.

For commercial licensing, partnership inquiries, or hosted-product trials, contact [licensing@anylegal.ai](mailto:licensing@anylegal.ai) or see <https://anylegal.ai>.
