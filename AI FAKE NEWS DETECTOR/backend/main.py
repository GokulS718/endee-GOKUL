"""
main.py — FastAPI Application Entry Point
==========================================
Exposes endpoint groups:
  POST /api/safety-check    — Web URL safety analysis
  POST /api/fact-check      — Hybrid RAG content fact-checking (Endee + Tavily + LLM)
  GET  /api/history         — Past analysis records (SQLite)
  GET  /api/seed-status     — Endee DB index info
  POST /api/seed            — Trigger dataset re-seeding (background task)
  GET  /api/health          — System health check
"""

import json
import logging
import datetime
import subprocess
import sys
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
from database import engine, get_db
from safety_check import check_url_safety
from rag_pipeline import run_fact_check_pipeline, get_vector_db_info
from scraper import extract_text_from_url

# ─── Bootstrap ────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger(__name__)

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Fake News & Web Safety Detector API",
    description=(
        "Hybrid RAG fact-checking pipeline: Endee vector DB + Tavily live search + "
        "Google Gemini LLM. Includes URL safety analysis via Google Safe Browsing."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class SafetyCheckRequest(BaseModel):
    url: str

class SafetyCheckResponse(BaseModel):
    url: str
    status: str          # Safe | Suspicious | Dangerous | Unknown
    threat_type: Optional[str] = None
    detail: str

class FactCheckRequest(BaseModel):
    text: Optional[str] = None
    url:  Optional[str] = None

class FactCheckResponse(BaseModel):
    verdict:      str            # Real | Fake | Misleading
    confidence:   float          # 0-100
    explanation:  str
    key_signals:  List[str] = []
    sources:      List[str] = []
    safety_status: str = "Safe"
    vector_hits:  int = 0
    input_used:   str            # "text" | "url"
    note:         str = ""

class HistoryItem(BaseModel):
    id:               int
    user_input:       str
    input_type:       str
    prediction_result: str
    confidence_score: float
    safety_status:    str
    source_links:     List[str]
    timestamp:        str

    class Config:
        from_attributes = True

class SeedStatusResponse(BaseModel):
    available: bool
    index:     str
    count:     object   # int or "unknown"
    url:       str
    seeding_in_progress: bool = False

class SeedRequest(BaseModel):
    source: str = "all"   # "hf", "github", or "all"
    limit:  Optional[int] = None


# ─── Background seeding state ─────────────────────────────────────────────────
_seeding_in_progress = False


def _run_seed_background(source: str, limit: Optional[int]):
    global _seeding_in_progress
    _seeding_in_progress = True
    try:
        cmd = [sys.executable, "seed_endee.py", "--source", source]
        if limit:
            cmd += ["--limit", str(limit)]
        logger.info(f"Starting background seed: {' '.join(cmd)}")
        subprocess.run(cmd, cwd=str(__file__).replace("main.py", ""), timeout=600)
        logger.info("Background seeding complete.")
    except Exception as e:
        logger.error(f"Background seeding failed: {e}")
    finally:
        _seeding_in_progress = False


# ─── Health Check ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health():
    """System health check — returns API version and DB status."""
    db_info = get_vector_db_info()
    return {
        "status":        "ok",
        "version":       "3.0.0",
        "message":       "AI Safety & Fact Detector API Running",
        "endee_db":      db_info.get("available", False),
        "endee_vectors": db_info.get("count", 0),
    }


# ─── Endpoint 1: Web Safety Check ─────────────────────────────────────────────

@app.post("/api/safety-check", response_model=SafetyCheckResponse, tags=["Safety"])
def safety_check(request: SafetyCheckRequest):
    """
    Analyse a URL for phishing, malware, and social-engineering threats.
    Uses Google Safe Browsing API when configured; falls back to heuristics.
    """
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    result = check_url_safety(url)
    return SafetyCheckResponse(
        url=url,
        status=result["status"],
        threat_type=result.get("threat_type"),
        detail=result["detail"],
    )


# ─── Endpoint 2: Hybrid RAG Fact Check ────────────────────────────────────────

@app.post("/api/fact-check", response_model=FactCheckResponse, tags=["FactCheck"])
def fact_check(request: FactCheckRequest, db: Session = Depends(get_db)):
    """
    Perform a Hybrid RAG fact-check on provided text or a URL's scraped content.
    Pipeline: Endee vector DB → Tavily live search → Gemini LLM synthesis.
    """
    if not request.text and not request.url:
        raise HTTPException(status_code=400, detail="Provide either 'text' or 'url'.")

    input_type    = "url" if request.url else "text"
    content       = ""
    scrape_note   = ""
    safety_status = "Safe"

    # ── Extract text from URL if needed ──────────────────────────────────────
    if request.url:
        scrape_result = extract_text_from_url(str(request.url))
        content       = scrape_result.text
        scrape_note   = getattr(scrape_result, "note", "")

        safety_result = check_url_safety(str(request.url))
        safety_status = safety_result["status"]

        if safety_status == "Dangerous":
            return FactCheckResponse(
                verdict="Fake",
                confidence=99.0,
                explanation=f"This URL has been flagged as dangerous: {safety_result['detail']}",
                key_signals=["URL flagged by Safe Browsing", safety_result.get("threat_type", "")],
                sources=[],
                safety_status="Dangerous",
                vector_hits=0,
                input_used=input_type,
                note="Analysis halted: dangerous URL detected.",
            )
    else:
        content = request.text or ""

    if len(content.strip()) < 15:
        raise HTTPException(
            status_code=400,
            detail="Input too short. Please provide meaningful text (at least 15 characters).",
        )

    # ── Run the RAG pipeline ──────────────────────────────────────────────────
    try:
        pipeline_result = run_fact_check_pipeline(
            input_text=content,
            input_url=str(request.url) if request.url else "",
        )
    except Exception as exc:
        logger.error(f"Pipeline error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis pipeline error: {exc}")

    # ── Persist to SQLite ─────────────────────────────────────────────────────
    user_input_val = (str(request.url) if request.url else content)[:500]
    try:
        db_row = models.Query(
            user_input        = user_input_val,
            input_type        = input_type,
            prediction_result = pipeline_result["verdict"],
            confidence_score  = pipeline_result["confidence"],
            safety_status     = safety_status,
            source_links      = json.dumps(pipeline_result.get("sources", [])),
        )
        db.add(db_row)
        db.commit()
    except Exception as db_err:
        logger.error(f"DB write error: {db_err}")

    return FactCheckResponse(
        verdict       = pipeline_result["verdict"],
        confidence    = pipeline_result["confidence"],
        explanation   = pipeline_result["explanation"],
        key_signals   = pipeline_result.get("key_signals", []),
        sources       = pipeline_result.get("sources", []),
        safety_status = safety_status,
        vector_hits   = pipeline_result.get("vector_hits", 0),
        input_used    = input_type,
        note          = scrape_note,
    )


# ─── Backward-Compatible Legacy Endpoint ──────────────────────────────────────

@app.post("/analyze", tags=["Legacy"])
def analyze_legacy(request: FactCheckRequest, db: Session = Depends(get_db)):
    """Backward-compatible wrapper around /api/fact-check."""
    result = fact_check(request, db)
    return {
        "result":        result.verdict,
        "confidence":    result.confidence,
        "input_used":    result.input_used,
        "note":          result.note,
        "safety_status": result.safety_status,
        "sources":       result.sources,
    }


# ─── Endpoint 3: History ──────────────────────────────────────────────────────

@app.get("/api/history", response_model=List[HistoryItem], tags=["History"])
def get_history(limit: int = 10, db: Session = Depends(get_db)):
    """Return the most recent fact-check analyses from SQLite."""
    try:
        rows = (
            db.query(models.Query)
            .order_by(models.Query.timestamp.desc())
            .limit(max(1, min(limit, 50)))
            .all()
        )
        return [
            HistoryItem(
                id                = q.id,
                user_input        = q.user_input,
                input_type        = q.input_type,
                prediction_result = q.prediction_result,
                confidence_score  = q.confidence_score,
                safety_status     = getattr(q, "safety_status", "Safe"),
                source_links      = json.loads(getattr(q, "source_links", "[]")),
                timestamp         = q.timestamp.isoformat() + "Z" if q.timestamp else "",
            )
            for q in rows
        ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")


# ─── Endpoint 4: Endee DB Seed Status ─────────────────────────────────────────

@app.get("/api/seed-status", response_model=SeedStatusResponse, tags=["VectorDB"])
def seed_status():
    """
    Check the status of the Endee vector database index.
    Returns whether the index is available and how many vectors are stored.
    """
    info = get_vector_db_info()
    return SeedStatusResponse(
        available            = info.get("available", False),
        index                = info.get("index", "news_facts"),
        count                = info.get("count", 0),
        url                  = info.get("url", "http://localhost:8080/api/v1"),
        seeding_in_progress  = _seeding_in_progress,
    )


# ─── Endpoint 5: Trigger Re-Seeding ───────────────────────────────────────────

@app.post("/api/seed", tags=["VectorDB"])
def trigger_seed(request: SeedRequest, background_tasks: BackgroundTasks):
    """
    Admin endpoint: re-seed the Endee vector DB from HuggingFace / GitHub datasets.
    The seeding runs in the background — poll /api/seed-status to track progress.

    Body:
      { "source": "all" | "hf" | "github", "limit": 500 }
    """
    global _seeding_in_progress
    if _seeding_in_progress:
        return {"message": "Seeding already in progress. Check /api/seed-status.", "started": False}

    valid_sources = ("hf", "github", "all")
    source = request.source if request.source in valid_sources else "all"

    background_tasks.add_task(_run_seed_background, source, request.limit)
    return {
        "message": f"Seeding started (source={source}). Poll /api/seed-status for updates.",
        "started": True,
    }
