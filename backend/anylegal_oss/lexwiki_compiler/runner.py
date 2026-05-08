"""LexWiki compiler runner — main entry point.

Modes:
    --loop              Default in container. Polls workspaces forever.
    --once              Single pass, exit.
    --workspace <id>    Force-compile one workspace and exit.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def _setup_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def _write_heartbeat(state_dir: Path, name: str, payload: dict) -> None:
    """Persist a status marker the host can probe (matches observer pattern)."""
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / name).write_text(json.dumps(payload) + "\n", encoding='utf-8')
    except Exception as e:
        logger.warning(f"Failed to write heartbeat {name}: {e}")

def _run_once(cfg, target_workspace: Optional[str] = None) -> int:
    from . import compiler_job, poller

    if target_workspace:
        logger.info(f"Compiling single workspace: {target_workspace}")
        result = compiler_job.compile_workspace(target_workspace, cfg)
        logger.info(f"[{target_workspace}] {result}")
        _write_heartbeat(cfg.state_dir, "last_run.json", {"ts": time.time(), "result": result})
        return 0 if result.get("ok") else 1

    candidates = poller.find_candidates(
        debounce_seconds=cfg.debounce_seconds,
        limit=cfg.max_workspaces_per_pass,
    )
    logger.info(f"Pass found {len(candidates)} candidate workspace(s)")

    successes = 0
    failures = 0
    for wid in candidates:
        result = compiler_job.compile_workspace(wid, cfg)
        logger.info(f"[{wid}] {result}")
        if result.get("ok"):
            successes += 1
        else:
            failures += 1

    summary = {"ts": time.time(), "candidates": len(candidates), "ok": successes, "err": failures}
    _write_heartbeat(cfg.state_dir, "last_run.json", summary)
    return 0

def _run_loop(cfg) -> int:
    """Forever loop — sleeps cfg.poll_interval_seconds between passes."""
    stop = {"flag": False}

    def _on_signal(signum, _frame):
        logger.info(f"Received signal {signum}, exiting loop")
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    logger.info(
        f"Starting loop: poll={cfg.poll_interval_seconds}s "
        f"debounce={cfg.debounce_seconds}s "
        f"max_per_pass={cfg.max_workspaces_per_pass}"
    )
    _write_heartbeat(cfg.state_dir, "started.json", {"ts": time.time()})

    while not stop["flag"]:
        try:
            _run_once(cfg)
        except Exception:
            logger.exception("Run pass crashed; continuing loop")

        slept = 0
        while slept < cfg.poll_interval_seconds and not stop["flag"]:
            time.sleep(min(2, cfg.poll_interval_seconds - slept))
            slept += 2

    logger.info("Loop exited cleanly")
    return 0

def _verify_lexwiki_installed() -> bool:
    """Probe the deferred lexwiki import at startup.

    The compiler imports `from lexwiki.compile.compiler import WikiCompiler`
    lazily inside the per-workspace job, so a missing package would only
    surface days later on a user's first compile. Probing once at boot
    fails loud immediately and lets the runner exit cleanly instead of
    polling forever and crashing on the first candidate.
    """
    try:
        from lexwiki.compile.compiler import WikiCompiler  # noqa: F401
        return True
    except ImportError as e:
        logger.warning(
            "lexwiki package not importable (%s). Wiki compilation is "
            "disabled. To enable, install lexwiki in the compiler image "
            "(see backend/requirements.in for the pinned source) or "
            "comment out the lexwiki-compiler service in docker-compose.yml "
            "to silence this warning.",
            e,
        )
        return False


def main() -> int:
    _setup_logging()

    if not _verify_lexwiki_installed():
        return 0

    parser = argparse.ArgumentParser(prog="lexwiki_compiler")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--loop", action="store_true", help="Run forever (default in container)")
    mode.add_argument("--once", action="store_true", help="Single pass over candidates, then exit")
    parser.add_argument("--workspace", type=str, help="Compile a specific workspace ID and exit")
    args = parser.parse_args()

    from .config import Config
    try:
        cfg = Config.from_env()
    except RuntimeError as e:

        is_loop_mode = args.loop or not (args.once or args.workspace)
        if is_loop_mode and "required env var not set" in str(e):
            logger.warning(
                f"{e} — lexwiki-compiler exiting. Set the missing var in .env "
                "and `docker compose up -d lexwiki-compiler` to enable wiki "
                "compilation; the container's restart policy retries on its "
                "own cadence rather than this process holding open."
            )
            return 0
        logger.error(f"Bad config: {e}")
        return 2

    if args.workspace:
        return _run_once(cfg, target_workspace=args.workspace)

    if args.once:
        return _run_once(cfg)

    return _run_loop(cfg)

if __name__ == "__main__":
    sys.exit(main())
