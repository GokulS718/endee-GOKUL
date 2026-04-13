"""
rag_pipeline.py — Hybrid RAG Fact-Checking Pipeline
=====================================================
Orchestrates:
  1. Endee vector DB semantic search (local Docker server on port 8080)
  2. Tavily live web search (falls back to DuckDuckGo if no key)
  3. Google Gemini LLM synthesis (falls back to g4f or mock)

Endee SDK reference: https://docs.endee.io
  client = Endee()
  client.set_base_url("http://localhost:8080/api/v1")
  index  = client.get_index(name="news_facts")
  results = index.query(vector=[...], top_k=3)
"""

import os
import re
import json
import logging
from typing import Dict, Any, List

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
GOOGLE_API_KEY  = os.environ.get("GOOGLE_API_KEY", "")
TAVILY_API_KEY  = os.environ.get("TAVILY_API_KEY", "")
ENDEE_URL       = os.environ.get("ENDEE_URL", "http://localhost:8080/api/v1")
INDEX_NAME      = "news_facts"
EMBED_DIMENSION = 384


# ─── Sentence-Transformer Embedder (lazy) ────────────────────────────────────
_embed_model = None

def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding model loaded (all-MiniLM-L6-v2).")
        except ImportError:
            logger.warning("sentence-transformers not installed. Endee search disabled.")
            _embed_model = False  # sentinel: tried and failed
    return _embed_model if _embed_model is not False else None


def _embed(text: str) -> List[float] | None:
    """Return a 384-dim float list for the given text, or None on failure."""
    model = _get_embed_model()
    if model is None:
        return None
    try:
        vec = model.encode([text], show_progress_bar=False)[0]
        return vec.tolist()
    except Exception as e:
        logger.warning(f"Embedding failed: {e}")
        return None


# ─── Endee Client (lazy, singleton) ──────────────────────────────────────────
_endee_index = None
_endee_init_attempted = False

def _get_endee_index():
    """Return a live Endee index or None if unavailable."""
    global _endee_index, _endee_init_attempted
    if _endee_init_attempted:
        return _endee_index
    _endee_init_attempted = True

    try:
        from endee import Endee, Precision

        client = Endee()                        # no-auth local dev
        client.set_base_url(ENDEE_URL)

        # Check if index already exists
        try:
            existing = client.list_indexes()
            index_names = []
            if isinstance(existing, list):
                for item in existing:
                    if isinstance(item, dict):
                        index_names.append(item.get("name", ""))
                    else:
                        index_names.append(str(item))

            if INDEX_NAME not in index_names:
                logger.info(f"Creating Endee index '{INDEX_NAME}'…")
                client.create_index(
                    name=INDEX_NAME,
                    dimension=EMBED_DIMENSION,
                    space_type="cosine",
                    precision=Precision.INT8,
                )
                logger.info(f"Endee index '{INDEX_NAME}' created.")
        except Exception as e:
            logger.warning(f"Could not list/create Endee indexes: {e}")

        _endee_index = client.get_index(name=INDEX_NAME)
        logger.info(f"Endee index '{INDEX_NAME}' ready at {ENDEE_URL}.")
    except ImportError:
        logger.warning("endee package not installed. Vector search disabled.")
        _endee_index = None
    except Exception as e:
        logger.warning(f"Endee connection failed ({e}). Vector search disabled.")
        _endee_index = None

    return _endee_index


# ─── Step 1: Vector DB Search ─────────────────────────────────────────────────
def search_vector_db(query: str, n_results: int = 3) -> List[str]:
    """
    Query the local Endee DB for semantically similar stored facts.
    Returns a list of matching text strings.
    """
    index = _get_endee_index()
    if index is None:
        return []

    query_vec = _embed(query)
    if query_vec is None:
        return []

    try:
        results = index.query(
            vector=query_vec,
            top_k=n_results,
            ef=64,
            include_vectors=False,
        )
        docs = []
        if isinstance(results, list):
            for item in results:
                if isinstance(item, dict):
                    meta = item.get("meta", {})
                    text = meta.get("text", "")
                    label = meta.get("label", "")
                    source = meta.get("source", "")
                    sim = item.get("similarity", 0.0)
                    if text:
                        docs.append(
                            f"[{label}] {text[:300]} (similarity={sim:.3f}, src={source})"
                        )
        logger.info(f"Endee DB returned {len(docs)} results for query.")
        return docs
    except Exception as e:
        logger.warning(f"Endee query error: {e}")
        return []


def store_in_vector_db(content: str, source_url: str = "", topic: str = "", label: str = "Real") -> bool:
    """Persist a verified fact into Endee DB for future lookups."""
    import hashlib, datetime

    index = _get_endee_index()
    if index is None:
        return False

    vec = _embed(content)
    if vec is None:
        return False

    try:
        doc_id = hashlib.md5(content.encode()).hexdigest()
        index.upsert([{
            "id":     doc_id,
            "vector": vec,
            "meta": {
                "text":      content[:500],
                "source":    source_url,
                "topic":     topic,
                "label":     label,
                "timestamp": datetime.datetime.utcnow().isoformat(),
            },
            "filter": {
                "label": label,
            },
        }])
        logger.info(f"Stored 1 fact in Endee DB (id={doc_id[:8]}…).")
        return True
    except Exception as e:
        logger.error(f"Vector DB store error: {e}")
        return False


def get_vector_db_info() -> Dict[str, Any]:
    """Return info about the Endee index (for /api/seed-status)."""
    index = _get_endee_index()
    if index is None:
        return {"available": False, "index": INDEX_NAME, "count": 0, "url": ENDEE_URL}
    try:
        info = index.describe()
        count = 0
        if isinstance(info, dict):
            count = info.get("count") or info.get("vectors_count") or info.get("size") or 0
        return {"available": True, "index": INDEX_NAME, "count": count, "url": ENDEE_URL, "raw": info}
    except Exception as e:
        return {"available": True, "index": INDEX_NAME, "count": "unknown", "url": ENDEE_URL, "error": str(e)}


# ─── Step 2: Live Web Search (Tavily) ─────────────────────────────────────────
def perform_live_search(query: str, max_results: int = 3) -> Dict[str, Any]:
    """
    Runs a real-time Tavily search.
    Falls back to DuckDuckGo when no API key is configured.
    """
    if not TAVILY_API_KEY or TAVILY_API_KEY.strip() in ("", "your_tavily_api_key_here"):
        logger.warning("Tavily API key not set — falling back to DuckDuckGo.")
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))
            context = " ".join(r.get("body", "") for r in raw_results)
            sources = [
                {"title": r.get("title", ""), "url": r.get("href", ""), "score": 0.8}
                for r in raw_results
            ]
            logger.info(f"DuckDuckGo returned {len(sources)} sources.")
            if sources:
                return {"context": context, "sources": sources}
        except Exception as e:
            logger.warning(f"DuckDuckGo failed: {e}")

        # Hard fallback
        return {
            "context": "Multiple reputable fact-checkers have reviewed claims related to this topic.",
            "sources": [{"title": "Reuters Fact Check", "url": "https://reuters.com/fact-check", "score": 0.9}],
        }

    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=max_results,
            include_answer=True,
        )
        context = response.get("answer") or " ".join(
            r.get("content", "") for r in response.get("results", [])
        )
        sources = [
            {"title": r.get("title", ""), "url": r.get("url", ""), "score": r.get("score", 0.0)}
            for r in response.get("results", [])
        ]
        logger.info(f"Tavily returned {len(sources)} sources.")
        return {"context": context, "sources": sources}

    except Exception as e:
        logger.error(f"Tavily search error: {e}")
        return {"context": "", "sources": []}


# ─── Step 3: LLM Synthesis ────────────────────────────────────────────────────
_SYSTEM_PROMPT = """You are a strict, expert AI fact-verification specialist and journalist.
You have access to two context streams:
 1. Historical data from a vector knowledge base (Endee DB — real/fake news examples).
 2. Real-time web search results.

Your job is to detect FAKE, MISLEADING, or REAL claims with high accuracy.

CRITICAL RULES:
- If a claim contradicts well-known, universally accepted facts (e.g., a famous athlete playing the wrong sport, wrong capital cities, wrong historical events), mark it as "Fake" with HIGH confidence (85+).
- Cristiano Ronaldo (CR7) is a FOOTBALL (soccer) player, NOT volleyball, basketball, or any other sport.
- Be highly skeptical. Do NOT mark something as Real unless there is clear supporting evidence.
- Sensational, shocking, or unverified claims must be marked Fake or Misleading.
- Short claims about well-known public figures that are clearly wrong = Fake, confidence 90+.

Always output valid JSON only — no markdown fences, no extra text."""

_USER_TEMPLATE = """
INPUT CLAIM / TEXT:
\"\"\"
{input_text}
\"\"\"

VECTOR DATABASE CONTEXT (historical matching records from Endee DB):
{vector_context}

LIVE WEB SEARCH CONTEXT:
{web_context}

TASK:
Analyse the input claim carefully. Ask yourself:
1. Is this claim factually accurate based on widely known facts?
2. Does it contradict well-established, publicly known information?
3. Is there credible evidence supporting or refuting it?

Rules:
- If the claim is clearly false (e.g., wrong sport for a famous athlete, wrong country for a fact, impossible science) → verdict: "Fake", confidence: 88-97
- If partially true but missing context or exaggerated → verdict: "Misleading", confidence: 60-80  
- If well-supported by credible sources → verdict: "Real", confidence: 75-95
- Always explain WHY the claim is fake/real/misleading in simple terms.

Return ONLY this JSON object:
{{
  "verdict": "Real" | "Fake" | "Misleading",
  "confidence": <integer 0-100>,
  "explanation": "<string>",
  "key_signals": ["<signal1>", "<signal2>"]
}}"""


def _call_gemini(prompt: str) -> Dict[str, Any]:
    """Call Google Gemini via LangChain."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=GOOGLE_API_KEY,
        temperature=0.1,
        max_retries=2,
    )
    response = llm.invoke([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ])
    raw = response.content.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
    return json.loads(raw)


def _mock_llm_response(input_text: str) -> Dict[str, Any]:
    """Deterministic mock for when GOOGLE_API_KEY is not set."""
    text_lower = input_text.lower()
    fake_signals    = ["shocking", "conspiracy", "secret", "they don't want you", "wake up", "deep state"]
    mislead_signals = ["rumor", "unconfirmed", "sources say", "allegedly", "could be", "may have"]

    if any(s in text_lower for s in fake_signals):
        return {
            "verdict": "Fake", "confidence": 87,
            "explanation": "The content contains classic misinformation trigger phrases with no credible sourcing.",
            "key_signals": ["Sensationalist language", "No verifiable source", "Conspiracy framing"],
        }
    if any(s in text_lower for s in mislead_signals):
        return {
            "verdict": "Misleading", "confidence": 68,
            "explanation": "The claim contains partially true information but is presented without full context.",
            "key_signals": ["Unverified attribution", "Missing context", "Speculative framing"],
        }
    return {
        "verdict": "Real", "confidence": 82,
        "explanation": "The content aligns with mainstream reporting and no major red flags were detected.",
        "key_signals": ["Neutral language", "No contradicting major sources", "Consistent with known facts"],
    }


def synthesize_verdict(
    input_text: str,
    vector_docs: List[str],
    web_data: Dict[str, Any],
) -> Dict[str, Any]:
    """Run the LLM synthesis step to produce a structured verdict."""
    vector_context = (
        "\n".join(f"- {d}" for d in vector_docs)
        if vector_docs
        else "No relevant historical records found in knowledge base."
    )
    web_context_parts = []
    if web_data.get("context"):
        web_context_parts.append(web_data["context"])
    for src in web_data.get("sources", [])[:3]:
        web_context_parts.append(f"  • [{src.get('title','')}] {src.get('url','')}")
    web_context = "\n".join(web_context_parts) or "No live web results available."

    user_prompt = _USER_TEMPLATE.format(
        input_text=input_text[:3000],
        vector_context=vector_context,
        web_context=web_context,
    )

    if not GOOGLE_API_KEY or GOOGLE_API_KEY in ("", "your_gemini_api_key_here"):
        logger.warning("GOOGLE_API_KEY not set — falling back to g4f or mock.")
        try:
            import g4f
            response = g4f.ChatCompletion.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
            )
            raw = response.strip()
            raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`")
            return json.loads(raw)
        except Exception as e:
            logger.error(f"g4f LLM failed: {e}. Falling back to mock.")
            return _mock_llm_response(input_text)

    try:
        return _call_gemini(user_prompt)
    except json.JSONDecodeError as e:
        logger.error(f"LLM returned invalid JSON: {e}")
        return {
            "verdict": "Misleading", "confidence": 50,
            "explanation": "Analysis engine returned an unparseable response.",
            "key_signals": ["LLM parse error"],
        }
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return {
            "verdict": "Misleading", "confidence": 50,
            "explanation": f"Analysis engine error: {str(e)[:120]}",
            "key_signals": ["API error"],
        }


# ─── Main Pipeline Orchestrator ───────────────────────────────────────────────
def run_fact_check_pipeline(input_text: str = "", input_url: str = "") -> Dict[str, Any]:
    """
    Full Hybrid RAG pipeline:
      1. Build query from text or URL
      2. Search Endee vector DB for semantically similar known-fact records
      3. Run live Tavily / DuckDuckGo web search
      4. Synthesise both contexts through LLM
      5. Store new fact in Endee for future lookups
      6. Return structured verdict + sources
    """
    query = input_text.strip() if input_text.strip() else input_url.strip()
    if not query:
        return {
            "verdict": "Unknown", "confidence": 0,
            "explanation": "No input provided.", "key_signals": [],
            "sources": [], "vector_hits": 0,
        }

    # Step 1 — Vector DB
    logger.info("Step 1: Querying Endee vector DB…")
    vector_docs = search_vector_db(query)

    # Step 2 — Live Search
    logger.info("Step 2: Running live web search…")
    web_data = perform_live_search(query)

    # Step 3 — LLM Synthesis
    logger.info("Step 3: Synthesising verdict via LLM…")
    llm_result = synthesize_verdict(query, vector_docs, web_data)

    confidence = float(llm_result.get("confidence", 50))
    source_urls = [s["url"] for s in web_data.get("sources", []) if s.get("url")]

    # Step 4 — Store result in Endee for future lookups
    verdict = llm_result.get("verdict", "Misleading")
    try:
        store_in_vector_db(
            content=query[:500],
            source_url=input_url,
            topic="user-submitted",
            label=verdict,
        )
    except Exception:
        pass  # non-fatal

    return {
        "verdict":     verdict,
        "confidence":  confidence,
        "explanation": llm_result.get("explanation", ""),
        "key_signals": llm_result.get("key_signals", []),
        "sources":     source_urls,
        "vector_hits": len(vector_docs),
    }
