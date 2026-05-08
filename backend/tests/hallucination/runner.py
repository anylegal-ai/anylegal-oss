"""Run the hallucination test matrix and write JSON + Markdown reports.

Usage (from repo root):
    python -m tests.hallucination.runner --model moonshotai/kimi-k2.5 \
        --sizes 1,5,10,25,50 --out tests/hallucination/results/baseline.json

Requires OPENROUTER_API_KEY in environment (loaded from .env if present).
Each cell in the matrix is one LLM call. Total cost ~$0.05-0.20 per full run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv

# Make `anylegal_oss` importable and load .env / .env.local the same way the app does.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / ".env.local", override=True)

from openai import AsyncOpenAI  # noqa: E402

from tests.hallucination.classifier import classify  # noqa: E402
from tests.hallucination.prompts import TEST_PROMPTS  # noqa: E402
from tests.hallucination.workspaces import (  # noqa: E402
    FAKE_SESSION_ID,
    fake_prior_assistant_mentioning_docs,
    format_as_list_documents_result,
    make_workspace,
)


def load_prompts(path: str | None) -> List[Dict]:
    if not path:
        return TEST_PROMPTS
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    # Accept either [{...}, ...] or {"prompts": [...]}
    if isinstance(data, dict) and "prompts" in data:
        return data["prompts"]
    return data

DEFAULT_MODEL = "moonshotai/kimi-k2.5"
DEFAULT_SIZES = [1, 5, 10, 25, 50]

SYSTEM_PROMPT_PATH = (
    REPO_ROOT / "anylegal_oss" / "workspace" / "prompts" / "system_prompt.md"
)

# Marker of the block added in fix 399ac6b. Stripping everything between the
# header and the next blank line gives us the pre-fix system prompt for use
# as a negative control in the test harness.
FIX_MARKER_START = "**IMPORTANT — Referring to workspace documents in your reply text:**"


def load_system_prompt(strip_fix: bool = False) -> str:
    text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    if strip_fix and FIX_MARKER_START in text:
        before, after = text.split(FIX_MARKER_START, 1)
        # The fix block is delimited by a blank line followed by a new section header.
        # Cut up to (but not including) the next top-level heading or "**IMPORTANT".
        import re as _re
        m = _re.search(r"\n##\s|\n\*\*IMPORTANT", after)
        if m:
            after = after[m.start():]
        else:
            after = ""
        text = before.rstrip() + "\n\n" + after.lstrip()
    return text


def build_messages(system_prompt: str, filenames: List[str], user_prompt: str) -> List[Dict]:
    """Assemble a message history that puts the model in the same state Michael was in.

    Shape:
      - system: real system prompt (post-fix)
      - user: "Show me what's in my workspace" (simulated first turn)
      - assistant: tool_call to list_documents (simulated)
      - tool: list_documents result with the N filenames
      - assistant: short acknowledgement mentioning some of the files
      - user: the actual test prompt (retrieval-oriented)
    """
    listing = format_as_list_documents_result(filenames)
    prior_ack = fake_prior_assistant_mentioning_docs(filenames)
    workspace_header = (
        f"Workspace session id: {FAKE_SESSION_ID}\n"
        f"Document count: {len(filenames)}\n"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Show me what's in my workspace."},
        {
            "role": "assistant",
            "content": (
                f"{workspace_header}\n"
                f"Here are the files currently in your workspace:\n{listing}\n\n"
                f"{prior_ack}"
            ),
        },
        {"role": "user", "content": user_prompt},
    ]


async def run_one(
    client: AsyncOpenAI, model: str, messages: List[Dict],
    max_tokens: int = 600, temperature: float = 0.7,
) -> str:
    resp = await client.chat.completions.create(
        model=model, messages=messages, max_tokens=max_tokens, temperature=temperature
    )
    return resp.choices[0].message.content or ""


async def run_matrix(
    model: str,
    sizes: List[int],
    temperature: float = 0.7,
    strip_fix: bool = False,
    prompts: List[Dict] | None = None,
    concurrency: int = 20,
) -> Dict:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY not set in env. Add to .env.local.")

    system_prompt = load_system_prompt(strip_fix=strip_fix)
    prompts = prompts if prompts is not None else TEST_PROMPTS
    semaphore = asyncio.Semaphore(concurrency)

    async def gated(coro):
        async with semaphore:
            return await coro

    async with AsyncOpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=120.0,
    ) as client:
        cells = []
        for size in sizes:
            filenames = make_workspace(size)
            # Run all 10 prompts for this size concurrently (keeps it fast).
            tasks = []
            for prompt in prompts:
                msgs = build_messages(system_prompt, filenames, prompt["user"])
                tasks.append(gated(run_one(client, model, msgs, temperature=temperature)))
            t0 = time.time()
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - t0

            for prompt, response in zip(prompts, responses):
                if isinstance(response, Exception):
                    cells.append({
                        "size": size,
                        "prompt_id": prompt["id"],
                        "user": prompt["user"],
                        "response": None,
                        "error": repr(response),
                        "counts": {},
                        "hallucinated": None,
                        "findings": [],
                    })
                    continue
                result = classify(response)
                cells.append({
                    "size": size,
                    "prompt_id": prompt["id"],
                    "user": prompt["user"],
                    "response": response,
                    "counts": result.counts(),
                    "hallucinated": result.hallucinated(),
                    "hallucination_count": result.hallucination_count(),
                    "findings": [
                        {"kind": f.kind, "anchor": f.anchor, "target": f.target}
                        for f in result.findings
                    ],
                })
            print(
                f"  size={size:>2}  "
                f"{len(responses)} prompts in {elapsed:.1f}s  "
                f"hallucinated={sum(1 for c in cells[-len(responses):] if c.get('hallucinated'))}"
                f"/{len(responses)}",
                flush=True,
            )

        return {
            "meta": {
                "model": model,
                "sizes": sizes,
                "temperature": temperature,
                "strip_fix": strip_fix,
                "system_prompt_sha": _sha256(system_prompt),
                "system_prompt_chars": len(system_prompt),
                "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
                "prompt_count": len(prompts),
            },
            "cells": cells,
        }


def _sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def summarize_markdown(report: Dict) -> str:
    meta = report["meta"]
    cells = report["cells"]
    sizes = meta["sizes"]
    prompt_ids = sorted({c["prompt_id"] for c in cells})

    # Build size x prompt matrix of hallucination status.
    matrix = {(c["size"], c["prompt_id"]): c for c in cells}

    lines = []
    lines.append(f"# Link Hallucination Baseline")
    lines.append(f"- model: `{meta['model']}`")
    lines.append(f"- temperature: `{meta.get('temperature', 'n/a')}`")
    lines.append(f"- system_prompt sha: `{meta['system_prompt_sha']}` ({meta['system_prompt_chars']} chars)")
    lines.append(f"- timestamp: {meta['timestamp_utc']}")
    lines.append(f"- sizes: {sizes}")
    lines.append("")

    lines.append("## Hallucination rate by workspace size")
    lines.append("")
    lines.append("| size | hallucinated | total | rate |")
    lines.append("|---:|---:|---:|---:|")
    for size in sizes:
        halluc = sum(1 for c in cells if c["size"] == size and c.get("hallucinated"))
        total = sum(1 for c in cells if c["size"] == size and c.get("response") is not None)
        rate = (halluc / total * 100) if total else 0
        lines.append(f"| {size} | {halluc} | {total} | {rate:.0f}% |")
    lines.append("")

    lines.append("## Bare filename mentions by size (UX-adjacent signal)")
    lines.append("")
    lines.append("| size | avg bare_filename per response |")
    lines.append("|---:|---:|")
    for size in sizes:
        responses = [c for c in cells if c["size"] == size and c.get("response") is not None]
        if responses:
            avg = sum(c["counts"].get("bare_filename", 0) for c in responses) / len(responses)
        else:
            avg = 0
        lines.append(f"| {size} | {avg:.1f} |")
    lines.append("")

    # With many prompts (e.g. 100) a full grid is unreadable; only show prompts
    # that had at least one hallucination OR an error.
    interesting = []
    for pid in prompt_ids:
        for size in sizes:
            c = matrix.get((size, pid))
            if c is None:
                continue
            if c.get("hallucinated") or c.get("response") is None:
                interesting.append(pid)
                break

    if interesting:
        lines.append("## Cells that hallucinated or errored")
        lines.append("")
        header = "| prompt | " + " | ".join(f"size={s}" for s in sizes) + " |"
        sep = "|:---|" + "|".join(":---:" for _ in sizes) + "|"
        lines.append(header)
        lines.append(sep)
        for pid in interesting:
            row = [pid]
            for size in sizes:
                c = matrix.get((size, pid))
                if c is None:
                    cell = "?"
                elif c.get("response") is None:
                    cell = "E"
                elif c.get("hallucinated"):
                    cell = str(c.get("hallucination_count", 1))
                else:
                    cell = "."
                row.append(cell)
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    else:
        lines.append("## No hallucinations or errors across any cell")
        lines.append("")

    lines.append("## Example hallucinated link targets")
    lines.append("")
    seen_targets = set()
    example_count = 0
    for c in cells:
        if not c.get("hallucinated"):
            continue
        for f in c["findings"]:
            if f["kind"] != "hallucinated_workspace":
                continue
            key = f["target"][:80]
            if key in seen_targets:
                continue
            seen_targets.add(key)
            lines.append(f"- `[{f['anchor'][:40]}]({f['target'][:80]})`  (prompt=`{c['prompt_id']}`, size={c['size']})")
            example_count += 1
            if example_count >= 20:
                break
        if example_count >= 20:
            break
    lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES),
                    help="Comma-separated workspace sizes, e.g. 1,5,10,25,50")
    ap.add_argument("--out", default=None, help="Output JSON path (default: results/<timestamp>.json)")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--strip-fix", action="store_true",
                    help="Run with the hallucination-guard section removed from the system prompt "
                         "(negative control to prove the harness detects what it's meant to).")
    ap.add_argument("--prompts-file", default=None,
                    help="Path to a JSON file with a 'prompts' array (from generate_prompts.py). "
                         "Default: built-in 10-prompt TEST_PROMPTS.")
    ap.add_argument("--concurrency", type=int, default=20,
                    help="Max concurrent LLM calls (default 20).")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s.strip()]
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)

    if args.out:
        out_path = Path(args.out)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        out_path = results_dir / f"baseline_{stamp}.json"

    prompts = load_prompts(args.prompts_file)
    print(
        f"Running matrix: model={args.model} sizes={sizes} "
        f"prompts={len(prompts)} temperature={args.temperature} "
        f"strip_fix={args.strip_fix} concurrency={args.concurrency}"
    )
    report = asyncio.run(run_matrix(
        args.model, sizes,
        temperature=args.temperature,
        strip_fix=args.strip_fix,
        prompts=prompts,
        concurrency=args.concurrency,
    ))

    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    md_path = out_path.with_suffix(".md")
    md_path.write_text(summarize_markdown(report), encoding="utf-8")

    print(f"\nWrote {out_path}")
    print(f"Wrote {md_path}")
    print()
    # Echo summary to stdout for CI visibility.
    print(summarize_markdown(report))


if __name__ == "__main__":
    main()
