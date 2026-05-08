"""
Pluggable web-search provider abstraction for `web_search`.

Two providers ship with OSS — pick one by setting an API key (and optionally
`SEARCH_PROVIDER=serper|brave` to force a choice when both keys are present):

  - SERPER     (https://serper.dev)  → SERPER_API_KEY        (free tier ~2.5K/mo)
  - Brave      (https://brave.com/search/api/) → BRAVE_SEARCH_API_KEY  (free tier 2K/mo)

Auto-resolution order: explicit `SEARCH_PROVIDER` → SERPER if its key is set →
Brave if its key is set → None (caller surfaces "not configured" to the agent).

Each provider returns the same normalized shape:

    {
        "success": bool,
        "results": [{"title", "url", "description", "source", "position"?}],
        "error":   str,    # only when success=False
        "provider": str,   # "serper" | "brave"
    }

Adding a third provider (Tavily, Google CSE, You.com, etc.) is one new class
that conforms to `SearchProvider` and one entry in `_PROVIDER_REGISTRY`.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Protocol

import httpx

logger = logging.getLogger(__name__)

# Locale mapping is provider-agnostic; values are ISO-3166-1 alpha-2 (country)
# and ISO-639-1 (lang). Each provider translates these to its own param names.
JURISDICTION_LOCALE_MAPPING: Dict[str, Dict[str, str]] = {
    "ITALY": {"country": "it", "lang": "it"},
    "FRANCE": {"country": "fr", "lang": "fr"},
    "GERMANY": {"country": "de", "lang": "de"},
    "SPAIN": {"country": "es", "lang": "es"},
    "NETHERLANDS": {"country": "nl", "lang": "nl"},
    "BELGIUM": {"country": "be", "lang": "nl"},
    "SWITZERLAND": {"country": "ch", "lang": "de"},
    "AUSTRIA": {"country": "at", "lang": "de"},
    "PORTUGAL": {"country": "pt", "lang": "pt-PT"},
    "SWEDEN": {"country": "se", "lang": "sv"},
    "NORWAY": {"country": "no", "lang": "no"},
    "DENMARK": {"country": "dk", "lang": "da"},
    "FINLAND": {"country": "fi", "lang": "fi"},
    "POLAND": {"country": "pl", "lang": "pl"},
    "CZECH_REPUBLIC": {"country": "cz", "lang": "cs"},
    "HUNGARY": {"country": "hu", "lang": "hu"},
    "GREECE": {"country": "gr", "lang": "el"},
    "IRELAND": {"country": "ie", "lang": "en"},
    "LUXEMBOURG": {"country": "lu", "lang": "fr"},
    "ROMANIA": {"country": "ro", "lang": "ro"},
    "BULGARIA": {"country": "bg", "lang": "bg"},
    "CROATIA": {"country": "hr", "lang": "hr"},
    "SLOVENIA": {"country": "si", "lang": "sl"},
    "SLOVAKIA": {"country": "sk", "lang": "sk"},
    "ESTONIA": {"country": "ee", "lang": "et"},
    "LATVIA": {"country": "lv", "lang": "lv"},
    "LITHUANIA": {"country": "lt", "lang": "lt"},
    "CANADA": {"country": "ca", "lang": "en"},
    "MEXICO": {"country": "mx", "lang": "es"},
    "BRAZIL": {"country": "br", "lang": "pt"},
    "ARGENTINA": {"country": "ar", "lang": "es"},
    "COLOMBIA": {"country": "co", "lang": "es"},
    "CHILE": {"country": "cl", "lang": "es"},
    "PERU": {"country": "pe", "lang": "es"},
    "VENEZUELA": {"country": "ve", "lang": "es"},
    "URUGUAY": {"country": "uy", "lang": "es"},
    "PARAGUAY": {"country": "py", "lang": "es"},
    "BOLIVIA": {"country": "bo", "lang": "es"},
    "ECUADOR": {"country": "ec", "lang": "es"},
    "PANAMA": {"country": "pa", "lang": "es"},
    "COSTA_RICA": {"country": "cr", "lang": "es"},
    "GUATEMALA": {"country": "gt", "lang": "es"},
    "HONDURAS": {"country": "hn", "lang": "es"},
    "EL_SALVADOR": {"country": "sv", "lang": "es"},
    "NICARAGUA": {"country": "ni", "lang": "es"},
    "DOMINICAN_REPUBLIC": {"country": "do", "lang": "es"},
    "CUBA": {"country": "cu", "lang": "es"},
    "JAMAICA": {"country": "jm", "lang": "en"},
    "CHINA": {"country": "cn", "lang": "zh"},
    "JAPAN": {"country": "jp", "lang": "ja"},
    "SOUTH_KOREA": {"country": "kr", "lang": "ko"},
    "INDIA": {"country": "in", "lang": "en"},
    "INDONESIA": {"country": "id", "lang": "id"},
    "THAILAND": {"country": "th", "lang": "th"},
    "VIETNAM": {"country": "vn", "lang": "vi"},
    "MALAYSIA": {"country": "my", "lang": "ms"},
    "SINGAPORE": {"country": "sg", "lang": "en"},
    "PHILIPPINES": {"country": "ph", "lang": "en"},
    "TAIWAN": {"country": "tw", "lang": "zh-TW"},
    "HONG_KONG": {"country": "hk", "lang": "zh-HK"},
    "BANGLADESH": {"country": "bd", "lang": "bn"},
    "PAKISTAN": {"country": "pk", "lang": "en"},
    "SRI_LANKA": {"country": "lk", "lang": "en"},
    "MYANMAR": {"country": "mm", "lang": "my"},
    "CAMBODIA": {"country": "kh", "lang": "km"},
    "LAOS": {"country": "la", "lang": "lo"},
    "MONGOLIA": {"country": "mn", "lang": "mn"},
    "NEPAL": {"country": "np", "lang": "ne"},
    "UZBEKISTAN": {"country": "uz", "lang": "uz"},
    "KAZAKHSTAN": {"country": "kz", "lang": "kk"},
    "KYRGYZSTAN": {"country": "kg", "lang": "ky"},
    "TAJIKISTAN": {"country": "tj", "lang": "tg"},
    "TURKMENISTAN": {"country": "tm", "lang": "tk"},
    "AFGHANISTAN": {"country": "af", "lang": "fa"},
    "SAUDI_ARABIA": {"country": "sa", "lang": "ar"},
    "TURKEY": {"country": "tr", "lang": "tr"},
    "IRAN": {"country": "ir", "lang": "fa"},
    "ISRAEL": {"country": "il", "lang": "he"},
    "JORDAN": {"country": "jo", "lang": "ar"},
    "LEBANON": {"country": "lb", "lang": "ar"},
    "SYRIA": {"country": "sy", "lang": "ar"},
    "IRAQ": {"country": "iq", "lang": "ar"},
    "KUWAIT": {"country": "kw", "lang": "ar"},
    "QATAR": {"country": "qa", "lang": "ar"},
    "BAHRAIN": {"country": "bh", "lang": "ar"},
    "OMAN": {"country": "om", "lang": "ar"},
    "YEMEN": {"country": "ye", "lang": "ar"},
    "CYPRUS": {"country": "cy", "lang": "el"},
    "GEORGIA": {"country": "ge", "lang": "ka"},
    "ARMENIA": {"country": "am", "lang": "hy"},
    "AZERBAIJAN": {"country": "az", "lang": "az"},
    "SOUTH_AFRICA": {"country": "za", "lang": "en"},
    "EGYPT": {"country": "eg", "lang": "ar"},
    "NIGERIA": {"country": "ng", "lang": "en"},
    "KENYA": {"country": "ke", "lang": "en"},
    "ETHIOPIA": {"country": "et", "lang": "am"},
    "GHANA": {"country": "gh", "lang": "en"},
    "UGANDA": {"country": "ug", "lang": "en"},
    "TANZANIA": {"country": "tz", "lang": "en"},
    "MOZAMBIQUE": {"country": "mz", "lang": "pt"},
    "MADAGASCAR": {"country": "mg", "lang": "mg"},
    "CAMEROON": {"country": "cm", "lang": "fr"},
    "IVORY_COAST": {"country": "ci", "lang": "fr"},
    "ANGOLA": {"country": "ao", "lang": "pt"},
    "MOROCCO": {"country": "ma", "lang": "ar"},
    "ALGERIA": {"country": "dz", "lang": "ar"},
    "TUNISIA": {"country": "tn", "lang": "ar"},
    "LIBYA": {"country": "ly", "lang": "ar"},
    "SUDAN": {"country": "sd", "lang": "ar"},
    "ZAMBIA": {"country": "zm", "lang": "en"},
    "ZIMBABWE": {"country": "zw", "lang": "en"},
    "BOTSWANA": {"country": "bw", "lang": "en"},
    "NAMIBIA": {"country": "na", "lang": "en"},
    "SENEGAL": {"country": "sn", "lang": "fr"},
    "MALI": {"country": "ml", "lang": "fr"},
    "BURKINA_FASO": {"country": "bf", "lang": "fr"},
    "NIGER": {"country": "ne", "lang": "fr"},
    "CHAD": {"country": "td", "lang": "fr"},
    "RWANDA": {"country": "rw", "lang": "en"},
    "BURUNDI": {"country": "bi", "lang": "fr"},
    "SOMALIA": {"country": "so", "lang": "ar"},
    "DJIBOUTI": {"country": "dj", "lang": "fr"},
    "ERITREA": {"country": "er", "lang": "ti"},
    "GAMBIA": {"country": "gm", "lang": "en"},
    "GUINEA": {"country": "gn", "lang": "fr"},
    "SIERRA_LEONE": {"country": "sl", "lang": "en"},
    "LIBERIA": {"country": "lr", "lang": "en"},
    "TOGO": {"country": "tg", "lang": "fr"},
    "BENIN": {"country": "bj", "lang": "fr"},
    "MAURITANIA": {"country": "mr", "lang": "ar"},
    "CAPE_VERDE": {"country": "cv", "lang": "pt"},
    "SAO_TOME_PRINCIPE": {"country": "st", "lang": "pt"},
    "SEYCHELLES": {"country": "sc", "lang": "en"},
    "MAURITIUS": {"country": "mu", "lang": "en"},
    "COMOROS": {"country": "km", "lang": "ar"},
    "AUSTRALIA": {"country": "au", "lang": "en"},
    "NEW_ZEALAND": {"country": "nz", "lang": "en"},
    "FIJI": {"country": "fj", "lang": "en"},
    "PAPUA_NEW_GUINEA": {"country": "pg", "lang": "en"},
    "SOLOMON_ISLANDS": {"country": "sb", "lang": "en"},
    "VANUATU": {"country": "vu", "lang": "en"},
    "SAMOA": {"country": "ws", "lang": "en"},
    "TONGA": {"country": "to", "lang": "en"},
    "PALAU": {"country": "pw", "lang": "en"},
    "MICRONESIA": {"country": "fm", "lang": "en"},
    "MARSHALL_ISLANDS": {"country": "mh", "lang": "en"},
    "KIRIBATI": {"country": "ki", "lang": "en"},
    "NAURU": {"country": "nr", "lang": "en"},
    "TUVALU": {"country": "tv", "lang": "en"},
    "UAE": {"country": "ae", "lang": "ar"},
    "USA": {"country": "us", "lang": "en"},
    "UK": {"country": "gb", "lang": "en"},
    "RUSSIA": {"country": "ru", "lang": "ru"},
    "UKRAINE": {"country": "ua", "lang": "uk"},
    "BELARUS": {"country": "by", "lang": "be"},
    "MOLDOVA": {"country": "md", "lang": "ro"},
    "GENERAL": {"country": "us", "lang": "en"},
}


class SearchProvider(Protocol):
    """Minimal contract for a web-search backend."""
    name: str

    def is_configured(self) -> bool: ...

    async def search(
        self,
        query: str,
        locale: Optional[Dict[str, str]],
        count: int,
    ) -> Dict[str, Any]: ...


class SerperProvider:
    """SERPER (https://serper.dev) — Google SERP via API.

    Free tier: ~2.5K queries/mo (no card). Returns Google's organic results
    plus an optional knowledgeGraph entry for entity-style queries.
    """
    name = "serper"
    _ENDPOINT = "https://google.serper.dev/search"

    def is_configured(self) -> bool:
        return bool(os.getenv("SERPER_API_KEY"))

    async def search(self, query, locale, count):
        api_key = os.getenv("SERPER_API_KEY", "")
        # Over-request slightly to give room for the kg entry + ordering jitter.
        payload: Dict[str, Any] = {"q": query, "num": count + 5}
        if locale:
            if "country" in locale:
                payload["gl"] = locale["country"]
            if "lang" in locale:
                payload["hl"] = locale["lang"]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    self._ENDPOINT,
                    json=payload,
                    headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                )
            if resp.status_code != 200:
                logger.error(f"[serper] {resp.status_code}: {resp.text[:300]}")
                return {
                    "success": False,
                    "provider": self.name,
                    "error": f"SERPER returned status {resp.status_code}",
                    "results": [],
                }
            data = resp.json()
            results: List[Dict[str, Any]] = []
            kg = data.get("knowledgeGraph") or {}
            if kg.get("website"):
                title = f"{kg.get('title', '')} - {kg.get('type', '')}".strip(" -")
                results.append({
                    "title": title,
                    "url": kg["website"],
                    "description": kg.get("description", ""),
                    "source": "knowledge_graph",
                })
            for item in data.get("organic", []) or []:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "description": item.get("snippet", ""),
                    "position": item.get("position"),
                    "source": "organic",
                })
            return {"success": True, "provider": self.name, "results": results[:count]}
        except httpx.TimeoutException:
            return {"success": False, "provider": self.name, "error": "Search request timed out", "results": []}
        except Exception as e:
            logger.error(f"[serper] unexpected: {e}")
            return {"success": False, "provider": self.name, "error": f"SERPER call failed: {e}", "results": []}


class BraveProvider:
    """Brave Search API (https://brave.com/search/api/).

    Free tier: 2K queries/mo (no card; rate-limited to 1 req/sec).
    """
    name = "brave"
    _ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
    _MAX_COUNT = 20  # Brave caps at 20 per request

    def is_configured(self) -> bool:
        return bool(os.getenv("BRAVE_SEARCH_API_KEY"))

    async def search(self, query, locale, count):
        api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
        params: Dict[str, Any] = {
            "q": query,
            "count": min(count, self._MAX_COUNT),
        }
        if locale:
            if "country" in locale:
                params["country"] = locale["country"]
            if "lang" in locale:
                # Brave wants ISO 639-1 only (e.g. "en", not "en-US").
                params["search_lang"] = locale["lang"].split("-", 1)[0]

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(
                    self._ENDPOINT,
                    params=params,
                    headers={
                        "X-Subscription-Token": api_key,
                        "Accept": "application/json",
                        "Accept-Encoding": "gzip",
                    },
                )
            if resp.status_code != 200:
                logger.error(f"[brave] {resp.status_code}: {resp.text[:300]}")
                return {
                    "success": False,
                    "provider": self.name,
                    "error": f"Brave returned status {resp.status_code}",
                    "results": [],
                }
            data = resp.json()
            results: List[Dict[str, Any]] = []
            infobox = (data.get("infobox") or {}).get("results") or []
            for item in infobox:
                if item.get("url"):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item["url"],
                        "description": item.get("description", "") or item.get("long_desc", ""),
                        "source": "infobox",
                    })
            web_results = ((data.get("web") or {}).get("results")) or []
            for idx, item in enumerate(web_results, start=1):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "description": item.get("description", ""),
                    "position": idx,
                    "source": "organic",
                })
            return {"success": True, "provider": self.name, "results": results[:count]}
        except httpx.TimeoutException:
            return {"success": False, "provider": self.name, "error": "Search request timed out", "results": []}
        except Exception as e:
            logger.error(f"[brave] unexpected: {e}")
            return {"success": False, "provider": self.name, "error": f"Brave call failed: {e}", "results": []}


# Registry order is the auto-resolution preference: SERPER first (preserves
# the existing default for installs that already have only SERPER set), Brave
# second, future providers append.
_PROVIDER_REGISTRY: List[SearchProvider] = [SerperProvider(), BraveProvider()]


def resolve_provider() -> Optional[SearchProvider]:
    """Pick the active provider. Returns None if nothing is configured."""
    explicit = (os.getenv("SEARCH_PROVIDER") or "").lower().strip()
    if explicit in {"", "auto"}:
        for p in _PROVIDER_REGISTRY:
            if p.is_configured():
                return p
        return None
    for p in _PROVIDER_REGISTRY:
        if p.name == explicit:
            if not p.is_configured():
                logger.warning(
                    f"SEARCH_PROVIDER={explicit!r} is set but its API key is missing — "
                    f"web_search will return 'not configured' until the key is set."
                )
                return p  # let the provider's own search() return the proper error
            return p
    available = ", ".join(p.name for p in _PROVIDER_REGISTRY)
    logger.warning(
        f"SEARCH_PROVIDER={explicit!r} is unknown (known: {available}); "
        "falling back to auto-resolution."
    )
    for p in _PROVIDER_REGISTRY:
        if p.is_configured():
            return p
    return None


def configured_provider_names() -> List[str]:
    """Useful for diagnostics / logging — which providers have keys right now."""
    return [p.name for p in _PROVIDER_REGISTRY if p.is_configured()]
