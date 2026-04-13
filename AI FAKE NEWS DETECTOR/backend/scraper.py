"""
scraper.py — Robust multi-layer web scraper for the AI Fake News Detector.

Extraction priority:
  1. cloudscraper  (bypasses Cloudflare / JS-challenge pages)
  2. requests      (fast fallback with full browser headers)
  3. <meta> tags   (title + description — works even on 403 pages)
  4. URL tokens    (last resort: parse readable words from the URL itself)

The function NEVER raises an exception.  It always returns a ScrapeResult
named-tuple so the caller can decide how to handle partial / blocked content.
"""

import logging
import re
from collections import namedtuple
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional cloudscraper import (try, don't crash if not installed yet)
# ---------------------------------------------------------------------------
try:
    import cloudscraper as _cloudscraper
    _CLOUDSCRAPER_AVAILABLE = True
except ImportError:
    _CLOUDSCRAPER_AVAILABLE = False
    logger.warning("cloudscraper not installed — falling back to requests only.")

# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------
ScrapeResult = namedtuple(
    "ScrapeResult",
    ["text", "blocked", "note"],
    defaults=["", False, ""]
)

# ---------------------------------------------------------------------------
# Trusted & satire domain lists (mirrors ml_model.py — keep in sync)
# ---------------------------------------------------------------------------
TRUSTED_DOMAINS = [
    'github.com', 'google.com', 'microsoft.com', 'apple.com',
    'bbc.com', 'bbc.co.uk', 'reuters.com', 'apnews.com',
    'nytimes.com', 'washingtonpost.com', 'theguardian.com',
    'nature.com', 'sciencemag.org', 'sciencedirect.com',
    'who.int', 'cdc.gov', 'nasa.gov', 'wikipedia.org',
    'stackoverflow.com', 'techcrunch.com', 'wired.com',
]

# ---------------------------------------------------------------------------
# Full Chrome 124 browser header set
# ---------------------------------------------------------------------------
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    "DNT": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_trusted(url: str) -> bool:
    host = urlparse(url.lower()).netloc
    return any(d in host for d in TRUSTED_DOMAINS)


def _extract_from_soup(soup: BeautifulSoup) -> str:
    """Parse BeautifulSoup object → clean article text."""
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "iframe"]):
        tag.decompose()

    # 1. Article / main content tags
    for container_tag in ("article", "main", '[role="main"]'):
        container = soup.find(container_tag)
        if container:
            text = container.get_text(separator=" ", strip=True)
            if len(text) > 200:
                return text

    # 2. Paragraph tags
    paragraphs = soup.find_all("p")
    text = " ".join(p.get_text(separator=" ", strip=True) for p in paragraphs)
    if len(text.strip()) > 100:
        return text.strip()

    # 3. Full body fallback
    body = soup.find("body")
    if body:
        text = body.get_text(separator=" ", strip=True)
        if text.strip():
            return text.strip()

    return ""


def _extract_meta(html_bytes: bytes, url: str) -> str:
    """
    Extract <title> and <meta name="description"> from raw HTML bytes.
    Returns a short text blob suitable for keyword scoring.
    """
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
        parts = []

        title = soup.find("title")
        if title:
            parts.append(title.get_text(strip=True))

        for meta in soup.find_all("meta"):
            name = meta.get("name", "").lower()
            prop = meta.get("property", "").lower()
            content = meta.get("content", "").strip()
            if content and name in ("description", "keywords") or \
               prop in ("og:description", "og:title", "twitter:title",
                        "twitter:description"):
                parts.append(content)

        return " ".join(parts)
    except Exception:
        return ""


def _text_from_url_tokens(url: str) -> str:
    """Last-resort: extract readable words from the URL path."""
    try:
        path = unquote(urlparse(url).path)
        words = re.sub(r"[_\-/]+", " ", path).strip()
        return words if len(words) > 10 else ""
    except Exception:
        return ""


def _fetch_with_requests(url: str) -> tuple[bytes | None, int]:
    """
    Try fetching with requests.  Returns (content_bytes, status_code).
    Returns (None, status_code) on HTTP error but still gives us the body
    so we can pull <meta> tags even from a 403 response.
    """
    try:
        session = requests.Session()
        session.headers.update(_BROWSER_HEADERS)
        resp = session.get(url, timeout=15, allow_redirects=True)
        return resp.content, resp.status_code
    except requests.exceptions.RequestException as exc:
        logger.warning("requests failed for %s: %s", url, exc)
        return None, 0


def _fetch_with_cloudscraper(url: str) -> tuple[bytes | None, int]:
    """Try fetching with cloudscraper (handles Cloudflare JS challenges)."""
    if not _CLOUDSCRAPER_AVAILABLE:
        return None, 0
    try:
        scraper = _cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        resp = scraper.get(url, timeout=20)
        return resp.content, resp.status_code
    except Exception as exc:
        logger.warning("cloudscraper failed for %s: %s", url, exc)
        return None, 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text_from_url(url: str) -> ScrapeResult:
    """
    Robustly scrape ``url`` and return a :class:`ScrapeResult`.

    Layers:
      1. cloudscraper  → full article text
      2. requests      → full article text
      3. Either engine's raw response → meta-tag extraction
      4. URL tokens    → last resort

    The function **never raises**.  Check ``result.blocked`` to know whether
    content is partial.  ``result.note`` carries a human-readable explanation.

    Args:
        url: The web address to scrape.

    Returns:
        ScrapeResult(text, blocked, note)
    """
    trusted = _is_trusted(url)
    raw_content: bytes | None = None

    # ── Layer 1: cloudscraper ────────────────────────────────────────────────
    content, status = _fetch_with_cloudscraper(url)
    if content and status < 400:
        soup = BeautifulSoup(content, "html.parser")
        text = _extract_from_soup(soup)
        if len(text) > 100:
            logger.info("cloudscraper succeeded for %s (%d chars)", url, len(text))
            return ScrapeResult(text=text, blocked=False, note="")
        raw_content = content  # keep for meta extraction

    # ── Layer 2: requests ────────────────────────────────────────────────────
    if not raw_content:
        content, status = _fetch_with_requests(url)
        if content and status < 400:
            soup = BeautifulSoup(content, "html.parser")
            text = _extract_from_soup(soup)
            if len(text) > 100:
                logger.info("requests succeeded for %s (%d chars)", url, len(text))
                return ScrapeResult(text=text, blocked=False, note="")
        if content:
            raw_content = content  # 403 body may still have meta tags

    # ── Layer 3: meta-tag extraction from whatever response we got ───────────
    if raw_content:
        meta_text = _extract_meta(raw_content, url)
        if meta_text.strip():
            note = "High Security Site Detected — Basic Analysis Performed"
            logger.info("Meta extraction used for %s: %r", url, meta_text[:80])
            return ScrapeResult(text=meta_text, blocked=True, note=note)

    # ── Layer 4: URL tokens (absolute last resort) ───────────────────────────
    token_text = _text_from_url_tokens(url)
    if token_text:
        note = "High Security Site Detected — Basic Analysis Performed"
        return ScrapeResult(text=token_text, blocked=True, note=note)

    # ── Total failure — still don't crash; let the model handle it ──────────
    if trusted:
        # Trusted domains get a free pass with empty text (domain check wins)
        return ScrapeResult(text="", blocked=True,
                            note="Trusted domain — content protected")
    return ScrapeResult(
        text="",
        blocked=True,
        note="High Security Site Detected — Basic Analysis Performed"
    )
