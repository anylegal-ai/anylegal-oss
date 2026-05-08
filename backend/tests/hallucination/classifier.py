"""Classify links in assistant-produced text.

Categories:
  - valid_workspace: matches the real preview route
  - hallucinated_workspace: markdown link whose target looks like it's trying
    to point to a workspace document but uses an invented URL shape
  - external: http(s) to a real external domain (passthrough, legit)
  - bare_filename: a `.docx`/`.xlsx`/`.pdf` filename mentioned in plain text
    without a link wrapper — not broken per se, but a UX signal that the user
    may try to click or ask "where is it?"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Dict

MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HTTP_URL = re.compile(r"https?://[^\s)>\"']+")
DOC_EXT = re.compile(r"\b[\w.\-]+?\.(?:docx|doc|xlsx|xls|pptx|ppt|pdf)\b", re.IGNORECASE)

# The one URL shape that would actually work. Pattern is intentionally broad.
VALID_WORKSPACE = re.compile(r"/api/v1/editor/workspace/sessions/[\w\-]+/docx/preview/")

# Known-bad shapes we've seen the model invent. This list will grow.
HALLUCINATED_PATTERNS = [
    re.compile(r"^/workspace/"),
    re.compile(r"^/documents/"),
    re.compile(r"^/download/"),
    re.compile(r"^sandbox:"),
    re.compile(r"^file://"),
    re.compile(r"^anylegal://"),
    re.compile(r"^/api/documents/"),
    re.compile(r"^\./"),
    re.compile(r"^/files/"),
]


@dataclass
class LinkFinding:
    kind: str  # valid_workspace | hallucinated_workspace | external | bare_filename | unknown
    anchor: str
    target: str


@dataclass
class ClassificationResult:
    findings: List[LinkFinding] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for f in self.findings:
            c[f.kind] = c.get(f.kind, 0) + 1
        return c

    def hallucination_count(self) -> int:
        return sum(1 for f in self.findings if f.kind == "hallucinated_workspace")

    def hallucinated(self) -> bool:
        return self.hallucination_count() > 0


def _looks_like_doc(text: str) -> bool:
    return bool(DOC_EXT.search(text))


def _classify_target(anchor: str, target: str) -> str:
    if VALID_WORKSPACE.search(target):
        return "valid_workspace"
    # If the target is an absolute http(s) link, assume external (legit research citation, not a workspace path).
    if target.startswith("http://") or target.startswith("https://"):
        # An http link to our own domain that looks workspace-y is still hallucinated.
        if re.search(r"(?i)(anylegal\.ai|localhost)", target) and (
            "/workspace/" in target or "/documents/" in target or "/download/" in target
        ):
            return "hallucinated_workspace"
        return "external"
    # Relative or scheme-like path. Check hallucination patterns.
    for pat in HALLUCINATED_PATTERNS:
        if pat.search(target):
            return "hallucinated_workspace"
    # Target with a doc extension is almost certainly trying to be a workspace link.
    if _looks_like_doc(target):
        return "hallucinated_workspace"
    # Target paired with a docx-y anchor and a non-obvious shape: still suspicious.
    if _looks_like_doc(anchor):
        return "hallucinated_workspace"
    return "unknown"


def classify(text: str) -> ClassificationResult:
    result = ClassificationResult()
    if not text:
        return result

    # Markdown links
    for anchor, target in MARKDOWN_LINK.findall(text):
        kind = _classify_target(anchor, target)
        result.findings.append(LinkFinding(kind=kind, anchor=anchor, target=target))

    # Bare filenames not inside a markdown link already
    text_sans_links = MARKDOWN_LINK.sub("", text)
    for m in DOC_EXT.findall(text_sans_links):
        result.findings.append(
            LinkFinding(kind="bare_filename", anchor=m, target="")
        )

    return result
