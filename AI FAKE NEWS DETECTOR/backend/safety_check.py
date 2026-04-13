"""
safety_check.py — Web Safety Checker Module
Checks a URL against Google Safe Browsing API.
Falls back to a heuristic engine if no API key is set.
"""

import os
import re
import logging
from typing import Dict, Any

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SAFE_BROWSING_API_KEY = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "")

# Heuristic threat patterns (used as fallback)
PHISHING_PATTERNS = [
    r"login[-.]?verify", r"account[-.]?confirm", r"secure[-.]?update",
    r"paypal.*verify", r"bank.*login", r"\.tk$", r"\.gq$", r"\.ml$",
]
MALWARE_PATTERNS = [
    r"free.*download", r"crack.*software", r"keygen", r"warez",
    r"\.(exe|bat|cmd|scr|vbs)$",
]
SCAM_PATTERNS = [
    r"you.*won", r"claim.*prize", r"urgent.*offer", r"limited.*time.*free",
    r"bitcoin.*double", r"crypto.*giveaway",
]


def _heuristic_check(url: str) -> Dict[str, Any]:
    """Rule-based URL scanner as a fallback when no API key is configured."""
    url_lower = url.lower()
    
    for pattern in PHISHING_PATTERNS:
        if re.search(pattern, url_lower):
            return {
                "status": "Dangerous",
                "threat_type": "PHISHING",
                "detail": f"URL matches a known phishing pattern: '{pattern}'",
            }
    for pattern in MALWARE_PATTERNS:
        if re.search(pattern, url_lower):
            return {
                "status": "Dangerous",
                "threat_type": "MALWARE",
                "detail": f"URL matches a known malware distribution pattern: '{pattern}'",
            }
    for pattern in SCAM_PATTERNS:
        if re.search(pattern, url_lower):
            return {
                "status": "Suspicious",
                "threat_type": "SOCIAL_ENGINEERING",
                "detail": f"URL matches a potential scam pattern: '{pattern}'",
            }

    # Check for suspicious TLD combinations
    suspicious_tlds = [".xyz", ".top", ".win", ".club", ".icu"]
    if any(url_lower.endswith(tld) or f"{tld}/" in url_lower for tld in suspicious_tlds):
        return {
            "status": "Suspicious",
            "threat_type": "SUSPICIOUS_TLD",
            "detail": "URL uses a TLD commonly associated with low-trust domains.",
        }

    return {
        "status": "Safe",
        "threat_type": None,
        "detail": "No heuristic threats detected. API key not configured for real-time check.",
    }


def check_url_safety(url: str) -> Dict[str, Any]:
    """
    Primary entry point for URL safety checking.
    Uses Google Safe Browsing API if key is set, otherwise falls back to heuristics.
    
    Returns a dict with keys: status, threat_type, detail
    """
    if not url or not url.strip():
        return {"status": "Unknown", "threat_type": None, "detail": "No URL provided."}

    # Use real Google Safe Browsing API if key is available
    if SAFE_BROWSING_API_KEY and SAFE_BROWSING_API_KEY not in ("", "your_safe_browsing_api_key_here"):
        api_endpoint = (
            f"https://safebrowsing.googleapis.com/v4/threatMatches:find"
            f"?key={SAFE_BROWSING_API_KEY}"
        )
        payload = {
            "client": {"clientId": "ai-fakenews-detector", "clientVersion": "2.0"},
            "threatInfo": {
                "threatTypes": [
                    "MALWARE",
                    "SOCIAL_ENGINEERING",
                    "UNWANTED_SOFTWARE",
                    "POTENTIALLY_HARMFUL_APPLICATION",
                ],
                "platformTypes": ["ANY_PLATFORM"],
                "threatEntryTypes": ["URL"],
                "threatEntries": [{"url": url}],
            },
        }
        try:
            resp = requests.post(api_endpoint, json=payload, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            if data.get("matches"):
                match = data["matches"][0]
                threat_type = match.get("threatType", "UNKNOWN_THREAT")
                return {
                    "status": "Dangerous",
                    "threat_type": threat_type,
                    "detail": f"Google Safe Browsing flagged this URL for: {threat_type}",
                }
            return {
                "status": "Safe",
                "threat_type": None,
                "detail": "URL passed Google Safe Browsing check — no threats found.",
            }
        except requests.RequestException as e:
            logger.error(f"Safe Browsing API request failed: {e}. Falling back to heuristics.")
            return _heuristic_check(url)

    # Fallback mode
    logger.warning("GOOGLE_SAFE_BROWSING_API_KEY not set. Using heuristic fallback.")
    return _heuristic_check(url)
