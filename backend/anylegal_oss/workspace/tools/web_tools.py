"""
Web/Research Tool Implementations

Implements web search and fetch tools:
- web_search: Search the web for information (uses SERPER API)
- web_fetch: Fetch and extract content from URLs (uses httpx).
    Adds an in-process LRU cache (TTL-bounded) and a same-host redirect
    rule on top of plain httpx. Bot-protected / JS-rendered sites that
    httpx can't reach are out of scope for the OSS fetcher — extend with
    your own headless backend if you need them.
"""

import asyncio
import os
import logging
import json
import socket
from collections import OrderedDict
from ipaddress import ip_address
from time import monotonic
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
import httpx

from ._search_providers import (
    JURISDICTION_LOCALE_MAPPING,
    configured_provider_names,
    resolve_provider,
)

logger = logging.getLogger(__name__)

DEFAULT_SEARCH_COUNT = 5
MAX_SEARCH_COUNT = 10
DEFAULT_FETCH_TIMEOUT = 75
DEFAULT_MAX_CHARS = 125000
PDF_MAX_BYTES = 10 * 1024 * 1024
PDF_MAX_PAGES = 50

# In-process LRU cache for web_fetch results. Same shape as Claude Code's
# WebFetch cache — successful fetches are memoized for a short TTL so an
# agent that re-asks "fetch X again" within the same session doesn't pay
# the network cost twice. Bounded by a total-content-bytes cap; oldest
# entry evicts when the cap is exceeded.
_FETCH_CACHE_TTL = int(os.getenv("WEB_FETCH_CACHE_TTL_SECONDS", "900"))
_FETCH_CACHE_MAX_BYTES = int(os.getenv("WEB_FETCH_CACHE_MAX_BYTES", str(50 * 1024 * 1024)))

_fetch_cache: "OrderedDict[str, tuple]" = OrderedDict()
_fetch_cache_bytes = 0
_fetch_cache_lock = asyncio.Lock()


def _cache_key(url: str, extract_mode: str, max_chars: int) -> str:
    """Cache key: URL + extraction args (different extract_mode => different result)."""
    return f"{url}\x1f{extract_mode}\x1f{max_chars}"


async def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    async with _fetch_cache_lock:
        entry = _fetch_cache.get(key)
        if not entry:
            return None
        ts, _size, result = entry
        if monotonic() - ts > _FETCH_CACHE_TTL:
            _evict_locked(key)
            return None
        _fetch_cache.move_to_end(key)
        return result


async def _cache_put(key: str, result: Dict[str, Any]) -> None:
    if not result.get("success"):
        return
    content = result.get("content", "")
    size = len(content) if isinstance(content, str) else len(str(content))
    if size > _FETCH_CACHE_MAX_BYTES:
        return
    global _fetch_cache_bytes
    async with _fetch_cache_lock:
        _evict_locked(key)
        while _fetch_cache and _fetch_cache_bytes + size > _FETCH_CACHE_MAX_BYTES:
            _, (_, ev_size, _) = _fetch_cache.popitem(last=False)
            _fetch_cache_bytes -= ev_size
        _fetch_cache[key] = (monotonic(), size, result)
        _fetch_cache_bytes += size


def _evict_locked(key: str) -> None:
    """Remove a single entry; caller must hold _fetch_cache_lock."""
    global _fetch_cache_bytes
    entry = _fetch_cache.pop(key, None)
    if entry:
        _fetch_cache_bytes -= entry[1]


def _normalize_host(host: Optional[str]) -> str:
    """Lowercase host, strip leading 'www.' for same-host comparison."""
    if not host:
        return ""
    return host.lower().removeprefix("www.")

def _is_pdf_url(url: str) -> bool:
    """Detect if a URL points to a PDF by extension (case-insensitive, ignores query/fragment)."""
    path = urlparse(url).path.lower()
    return path.endswith('.pdf')

_BINARY_CONTENT_TYPE_PREFIXES = (
    "application/octet-stream",
    "application/zip",
    "application/x-",                                        
    "application/vnd.",                                                 
    "image/",
    "audio/",
    "video/",
    "font/",
)

def _sniff_pdf_bytes(body: bytes) -> bool:
    """True if the byte head looks like a PDF (`%PDF-` magic, possibly after a BOM)."""
    if not body:
        return False

    head = body.lstrip(b"\xef\xbb\xbf \r\n\t")[:5]
    return head == b"%PDF-"

def _looks_binary(content_type: str, body: bytes) -> bool:
    """
    Decide whether a response body is binary and must NOT be decoded as text.

    Order of evidence: explicit binary content-type beats anything; otherwise
    sniff the magic bytes (PDF, ZIP, PNG, JPEG, GIF, OGG, MP4-ish, ELF).
    Default to text if we have no signal — letting through a small bit of
    text-with-mojibake is cheaper than rejecting legitimate HTML.
    """
    ct = (content_type or "").lower().split(";", 1)[0].strip()
    if any(ct.startswith(p) for p in _BINARY_CONTENT_TYPE_PREFIXES):
        return True
    if not body:
        return False
    head = body[:8]
    binary_magic = (
        b"%PDF-",                 
        b"PK\x03\x04",                                 
        b"\x89PNG\r\n\x1a\n",      
        b"\xff\xd8\xff",           
        b"GIF87a",                
        b"GIF89a",                
        b"OggS",                  
        b"\x7fELF",                      
    )
    return any(head.startswith(m) for m in binary_magic)

def _extract_pdf_text(pdf_bytes: bytes, url: str, max_chars: int,
                      max_pages: Optional[int] = PDF_MAX_PAGES) -> Dict[str, Any]:
    """Extract markdown from PDF bytes using pymupdf4llm.

    Args:
        max_pages: Maximum pages to extract. None = all pages (no limit).

    Returns a standard web_fetch result dict.
    """
    try:
        import pymupdf
        import pymupdf4llm
    except ImportError:
        return {
            "success": False,
            "error": "PDF extraction unavailable: pymupdf4llm not installed",
            "url": url,
        }

    if len(pdf_bytes) > PDF_MAX_BYTES:
        return {
            "success": False,
            "error": f"PDF too large: {len(pdf_bytes) / 1024 / 1024:.1f} MB (limit: {PDF_MAX_BYTES // (1024 * 1024)} MB)",
            "url": url,
        }

    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse PDF: {e}",
            "url": url,
        }

    page_count = len(doc)
    if page_count == 0:
        doc.close()
        return {
            "success": False,
            "error": "PDF contains no pages",
            "url": url,
        }

    if max_pages is not None:
        pages_to_extract = list(range(min(page_count, max_pages)))
        truncated_pages = page_count > max_pages
    else:
        pages_to_extract = list(range(page_count))
        truncated_pages = False

    try:
        content = pymupdf4llm.to_markdown(doc, pages=pages_to_extract, write_images=False)
    except Exception as e:
        doc.close()
        return {
            "success": False,
            "error": f"PDF text extraction failed: {e}",
            "url": url,
        }
    finally:
        doc.close()

    if not content or len(content.strip()) < 10:
        return {
            "success": False,
            "error": "PDF appears to contain no extractable text (may be scanned/image-only)",
            "url": url,
        }

    truncated_chars = len(content) > max_chars
    if truncated_chars:
        content = content[:max_chars] + "\n\n[Content truncated...]"

    if truncated_pages:
        content += f"\n\n[Showing first {max_pages} of {page_count} pages]"

    return {
        "success": True,
        "url": url,
        "content": content,
        "content_type": "application/pdf",
        "length": len(content),
        "truncated": truncated_chars or truncated_pages,
        "source": "pymupdf4llm",
        "pdf_pages": page_count,
    }

async def web_search(
    query: str,
    jurisdiction: Optional[str] = None,
    count: int = DEFAULT_SEARCH_COUNT,
    **kwargs
) -> Dict[str, Any]:
    """
    Search the web through the configured search provider (SERPER or Brave).

    Provider is auto-resolved from API keys (`SERPER_API_KEY` / `BRAVE_SEARCH_API_KEY`),
    or pinned via `SEARCH_PROVIDER=serper|brave`. See _search_providers.py.

    Args:
        query: Search query
        jurisdiction: Optional jurisdiction to focus search (e.g. "SINGAPORE")
        count: Number of results (1-10)

    Returns:
        Dict with normalized search results, or error.
    """
    provider = resolve_provider()
    if provider is None:
        return {
            "success": False,
            "error": (
                "Web search not configured. Set SERPER_API_KEY (https://serper.dev) "
                "or BRAVE_SEARCH_API_KEY (https://brave.com/search/api/), then recreate "
                "the backend container."
            ),
            "fallback": "Consider using web_fetch with specific URLs instead.",
        }

    import re as _re
    stripped_query = _re.sub(r'[^\w]', '', query)
    if len(stripped_query) < 3:
        logger.warning(f"[WEB_SEARCH] Rejected garbage query: {query!r}")
        return {
            "success": False,
            "error": (
                f"Invalid search query: {query!r}. The query must contain meaningful "
                "search terms (at least 3 alphanumeric characters). Please provide a "
                "descriptive search query like 'unpaid shares transfer Singapore "
                "Companies Act'."
            ),
        }

    search_query = query
    if jurisdiction and jurisdiction.upper() != "GENERAL":
        search_query = f"{query} {jurisdiction} jurisdiction"

    count = max(1, min(count, MAX_SEARCH_COUNT))

    locale: Optional[Dict[str, str]] = None
    if jurisdiction:
        locale = JURISDICTION_LOCALE_MAPPING.get(jurisdiction.upper().strip())

    result = await provider.search(search_query, locale, count)

    return {
        "success": result.get("success", False),
        "provider": result.get("provider", provider.name),
        "query": query,
        "search_query": search_query,
        "jurisdiction": jurisdiction,
        "results": result.get("results", []),
        "count": len(result.get("results", [])),
        "configured_providers": configured_provider_names(),
        **({"error": result["error"]} if result.get("error") else {}),
    }

async def web_fetch(
    url: str,
    extract_mode: str = "markdown",
    max_chars: int = DEFAULT_MAX_CHARS,
    **kwargs
) -> Dict[str, Any]:
    """
    Fetch and extract content from a URL using httpx.

    Returns plain text/markdown extraction. JavaScript-heavy pages may
    require additional handling — consider extending with your own scraper.

    Args:
        url: URL to fetch
        extract_mode: 'markdown' or 'text'
        max_chars: Maximum characters to return

    Returns:
        Dict with extracted content or error
    """

    if not url.startswith(("http://", "https://")):
        return {
            "success": False,
            "error": "Invalid URL. Must start with http:// or https://",
            "url": url
        }

    try:
        hostname = urlparse(url).hostname
        if hostname:
            resolved = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            for family, stype, proto, canonname, sockaddr in resolved:
                ip = ip_address(sockaddr[0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return {
                        "success": False,
                        "error": "Access to private/internal networks is not allowed",
                        "url": url
                    }
    except (socket.gaierror, ValueError):
        pass                                                  

    cache_key = _cache_key(url, extract_mode, max_chars)
    cached = await _cache_get(cache_key)
    if cached is not None:
        return {**cached, "cached": True}

    if _is_pdf_url(url):
        result = await _fetch_pdf_with_httpx(url, max_chars)
    else:
        result = await _fetch_with_httpx(url, extract_mode, max_chars)

    await _cache_put(cache_key, result)
    return result

async def _follow_same_host(
    http: httpx.AsyncClient,
    url: str,
    accept: str,
    max_hops: int = 5,
) -> Dict[str, Any]:
    """GET the URL, manually following redirects but only when the next hop
    is on the same host as the initial URL (modulo a leading 'www.').

    Cross-host redirects are refused — that's the SSRF-ish leak we close
    here, since the initial DNS-level private-IP guard in `web_fetch`
    only sees the original hostname, not whatever a 3xx hands back.

    Returns the final 200 response, or a dict with `success: False` on a
    cross-host redirect, redirect chain >= max_hops, or non-200 status.
    """
    initial_host = _normalize_host(urlparse(url).hostname)
    current = url
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Accept": accept,
    }
    for hop in range(max_hops + 1):
        response = await http.get(current, headers=headers)
        if response.status_code in (301, 302, 303, 307, 308):
            if hop == max_hops:
                return {"success": False, "error": "Too many redirects", "url": url}
            location = response.headers.get("location", "")
            if not location:
                return {"success": False, "error": f"Redirect with no Location header (status {response.status_code})", "url": url}
            next_url = str(httpx.URL(current).join(location))
            next_host = _normalize_host(urlparse(next_url).hostname)
            if next_host and next_host != initial_host:
                return {
                    "success": False,
                    "error": f"Cross-host redirect refused: {initial_host} → {next_host}",
                    "url": url,
                }
            current = next_url
            continue
        return {"success": True, "response": response, "final_url": current}
    return {"success": False, "error": "Too many redirects", "url": url}


async def _fetch_pdf_with_httpx(url: str, max_chars: int) -> Dict[str, Any]:
    """Download a PDF via httpx and extract text with pymupdf4llm."""
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as http:
            hop_result = await _follow_same_host(http, url, accept="application/pdf,*/*")
            if not hop_result["success"]:
                return hop_result
            response = hop_result["response"]
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"PDF fetch returned status {response.status_code}",
                    "url": url,
                }
            return _extract_pdf_text(response.content, url, max_chars)

    except httpx.TimeoutException:
        return {"success": False, "error": "PDF fetch timed out after 40s", "url": url}
    except Exception as e:
        logger.error(f"httpx PDF fetch error: {e}")
        return {"success": False, "error": f"PDF fetch failed: {str(e)}", "url": url}

async def _fetch_with_httpx(
    url: str, extract_mode: str, max_chars: int
) -> Dict[str, Any]:
    """Fetch HTML/text via httpx with same-host redirect handling."""
    try:
        async with httpx.AsyncClient(timeout=40, follow_redirects=False) as http:
            hop_result = await _follow_same_host(
                http, url,
                accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            )
            if not hop_result["success"]:
                return hop_result
            response = hop_result["response"]
            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Fetch returned status {response.status_code}",
                    "url": url,
                }

            content_type = response.headers.get("content-type", "")
            raw_bytes = response.content

            if _looks_binary(content_type, raw_bytes):
                if _sniff_pdf_bytes(raw_bytes) or "pdf" in content_type.lower():
                    logger.info(f"httpx HTML path received PDF body for {url}; routing to PDF extractor")
                    return _extract_pdf_text(raw_bytes, url, max_chars)
                return {
                    "success": False,
                    "error": (
                        f"URL returned binary content ({content_type or 'unknown'}, "
                        f"{len(raw_bytes)} bytes) that is not a PDF. web_fetch only "
                        "handles HTML/text and PDFs."
                    ),
                    "url": url,
                }

            raw_content = response.text
            extracted = _extract_content(raw_content, extract_mode, content_type)

            if len(extracted) > max_chars:
                extracted = extracted[:max_chars] + "\n\n[Content truncated...]"

            return {
                "success": True,
                "url": url,
                "content": extracted,
                "content_type": content_type,
                "length": len(extracted),
                "truncated": len(raw_content) > max_chars,
                "source": "httpx",
            }

    except httpx.TimeoutException:
        return {"success": False, "error": "Request timed out after 40s", "url": url}
    except Exception as e:
        logger.error(f"httpx fetch error: {e}")
        return {"success": False, "error": f"Fetch failed: {str(e)}", "url": url}

def _extract_content(html: str, mode: str, content_type: str) -> str:
    """
    Extract readable content from HTML.

    Uses readability-lxml if available, falls back to basic extraction.
    """

    if "html" not in content_type.lower():
        return html

    try:

        from readability import Document
        doc = Document(html)

        if mode == "markdown":

            try:
                import html2text
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0
                return h.handle(doc.summary())
            except ImportError:

                return _html_to_text(doc.summary())
        else:
            return _html_to_text(doc.summary())

    except ImportError:

        logger.debug("readability-lxml not available, using basic extraction")
        return _basic_extract(html, mode)
    except Exception as e:
        logger.warning(f"Content extraction error: {e}")
        return _basic_extract(html, mode)

def _basic_extract(html: str, mode: str) -> str:
    """Basic HTML content extraction without external libraries."""
    import re

    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    if mode == "markdown":
        html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<li[^>]*>(.*?)</li>', r'- \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)

    html = re.sub(r'<[^>]+>', '', html)

    import html as html_module
    html = html_module.unescape(html)

    html = re.sub(r'\n\s*\n', '\n\n', html)
    html = re.sub(r' +', ' ', html)

    return html.strip()

def _html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    import re
    import html as html_module

    text = re.sub(r'<[^>]+>', ' ', html)

    text = html_module.unescape(text)

    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def web_search_sync(
    query: str,
    jurisdiction: Optional[str] = None,
    count: int = DEFAULT_SEARCH_COUNT,
    **kwargs
) -> Dict[str, Any]:
    """Synchronous wrapper for web_search."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(web_search(query, jurisdiction, count, **kwargs))

def web_fetch_sync(
    url: str,
    extract_mode: str = "markdown",
    max_chars: int = DEFAULT_MAX_CHARS,
    **kwargs
) -> Dict[str, Any]:
    """Synchronous wrapper for web_fetch."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(web_fetch(url, extract_mode, max_chars, **kwargs))

WEB_TOOLS = {
    "web_search": web_search_sync,
    "web_fetch": web_fetch_sync,
}

WEB_TOOLS_ASYNC = {
    "web_search": web_search,
    "web_fetch": web_fetch,
}
