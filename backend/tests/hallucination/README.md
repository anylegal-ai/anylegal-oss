# Hallucination harness — OSS demo

A regression harness for testing the agent's hallucination behavior on legal-shaped prompts. Bundled with AnyLegal OSS as a credibility artifact: *"we test our system."*

## What it does

Runs a configurable matrix of prompts × workspace context sizes through the actual `system_prompt.md` end-to-end via OpenRouter, classifies the agent's response for hallucination signatures, and writes JSON + Markdown reports.

## What it isn't

This is a **demo set**. The 8 prompts in `prompts.py` are innocuous starter examples — enough to demonstrate the harness end-to-end. They do NOT cover the full adversarial surface that production-grade legal-AI evaluation needs.

The production AnyLegal hallucination evaluation runs a much larger curated set (jailbreak attempts, link-insistence prompts, non-English adversarial variants, document-mention fabrications, citation fabrications, URL fabrications) — that set is part of the hosted product, not this OSS distribution.

## Running the harness

```bash
cd backend
source .venv/bin/activate
export OPENROUTER_API_KEY=<your-key>

# Quick smoke test
python -m tests.hallucination.runner --sizes 1 --max-prompts 1

# Full demo run (8 prompts × 7 sizes = 56 LLM calls, ~$0.10–0.30)
python -m tests.hallucination.runner \
    --sizes 1,5,10,25,50,75,100 \
    --out tests/hallucination/results/demo_run.json

# Negative control (confirms the harness actually detects hallucinations)
python -m tests.hallucination.runner --strip-fix \
    --out tests/hallucination/results/negative_control.json
```

## Acceptance target

For naturalistic prompts (the demo set), the hallucination rate should be near 0%. Some hallucinations on adversarial prompts are expected — track the *delta* vs. prior baseline rather than the absolute number.

## Production-grade evaluation

For comprehensive hallucination evaluation tied to your jurisdiction, model selection, and skill catalog — see [anylegal.ai](https://anylegal.ai). The production stack includes:

- ~100 curated adversarial prompts covering jailbreak / link-insistence / citation fabrication / document fabrication
- Multi-language adversarial variants (non-English contract review)
- Per-skill regression tracking (review / draft / docx-editing each have their own evaluation surface)
- Lawyer-review subset for redline-quality scoring
