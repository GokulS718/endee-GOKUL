"""
seed_endee.py — One-Time Endee Vector Database Seeder
======================================================
Downloads fake/real news datasets from:
  1. HuggingFace Hub  — 'liar' dataset  (~12K labelled statements)
  2. GitHub raw CSV   — public fake-news dataset (~6K articles)

Converts each record to a 384-dim sentence embedding (MiniLM),
then upserts all vectors into the Endee 'news_facts' index.

Usage:
    python seed_endee.py                    # full seed (HF + GitHub)
    python seed_endee.py --source hf        # HuggingFace only
    python seed_endee.py --source github    # GitHub CSV only
    python seed_endee.py --limit 500        # limit per source (fast test)
"""

import os
import sys
import time
import hashlib
import argparse
import logging
import requests
import io

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────────────────────────
ENDEE_URL       = os.getenv("ENDEE_URL", "http://localhost:8080/api/v1")
INDEX_NAME      = "news_facts"
EMBED_DIMENSION = 384
BATCH_SIZE      = 100

# GitHub public fake-news CSV (WELFake dataset — government ML repo)
GITHUB_CSV_URL = (
    "https://raw.githubusercontent.com/sumeetkr/AwesomeFakeNews/master/"
    "datasets/sample_LIAR.csv"
)
# Fallback GitHub CSV (smaller, always available)
GITHUB_FALLBACK_URL = (
    "https://raw.githubusercontent.com/jyotidabass/Detecting-fake-news/"
    "main/data/train.csv"
)


# ── Embedding model (lazy-loaded) ──────────────────────────────────────────────
_embed_model = None

def get_embed_model():
    global _embed_model
    if _embed_model is None:
        logger.info("Loading sentence-transformers model (all-MiniLM-L6-v2)…")
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Embedding model loaded ✓")
    return _embed_model


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return a list of 384-dim float vectors for each input text."""
    model = get_embed_model()
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=False)
    return embeddings.tolist()


# ── Endee client ───────────────────────────────────────────────────────────────
def get_endee_index():
    """Connect to local Endee server and get (or create) the news_facts index."""
    try:
        from endee import Endee, Precision
        client = Endee()
        client.set_base_url(ENDEE_URL)

        # Try to create index — if it already exists just proceed
        try:
            logger.info(f"Creating Endee index '{INDEX_NAME}' (dim={EMBED_DIMENSION})…")
            client.create_index(
                name=INDEX_NAME,
                dimension=EMBED_DIMENSION,
                space_type="cosine",
                precision=Precision.INT8,
            )
            logger.info(f"Index '{INDEX_NAME}' created ✓")
        except Exception as create_err:
            err_msg = str(create_err).lower()
            if "already exists" in err_msg or "conflict" in err_msg or "409" in err_msg:
                logger.info(f"Index '{INDEX_NAME}' already exists — will upsert into it.")
            else:
                # Unexpected error during creation
                raise

        return client.get_index(name=INDEX_NAME)

    except Exception as e:
        logger.error(f"Failed to connect to Endee at {ENDEE_URL}: {e}")
        logger.error("Make sure Docker is running: docker start endee-server")
        sys.exit(1)


# ── HuggingFace — LIAR dataset ─────────────────────────────────────────────────
def load_huggingface_liar(limit: int | None = None) -> list[dict]:
    """
    Download the LIAR dataset from HuggingFace.
    Returns list of {text, label, source} dicts.
    """
    logger.info("Fetching LIAR dataset from HuggingFace Hub…")
    try:
        from datasets import load_dataset
        ds = load_dataset("liar", split="train", trust_remote_code=True)

        # Normalise labels → binary real/fake
        label_map = {
            "true":        "Real",
            "mostly-true": "Real",
            "half-true":   "Misleading",
            "barely-true": "Misleading",
            "false":       "Fake",
            "pants-fire":  "Fake",
        }

        records = []
        for i, row in enumerate(ds):
            if limit and i >= limit:
                break
            statement = row.get("statement", "").strip()
            if len(statement) < 20:
                continue
            raw_label = row.get("label", "")
            label = label_map.get(raw_label, "Misleading")
            subject = row.get("subject", "") or ""
            speaker = row.get("speaker", "") or ""
            text = f"{statement}"
            records.append({
                "text":   text,
                "label":  label,
                "source": f"HuggingFace/LIAR | speaker: {speaker}",
                "topic":  subject[:80] if subject else "politics",
            })

        logger.info(f"Loaded {len(records)} records from LIAR dataset ✓")
        return records

    except Exception as e:
        logger.warning(f"HuggingFace load failed ({e}). Trying manual download…")
        return _manual_liar_download(limit)


def _manual_liar_download(limit: int | None = None) -> list[dict]:
    """Fallback: download LIAR TSV directly from GitHub."""
    LIAR_URL = (
        "https://raw.githubusercontent.com/thiagorainmaker77/"
        "liar_dataset/master/train.tsv"
    )
    label_map = {
        "true":        "Real",
        "mostly-true": "Real",
        "half-true":   "Misleading",
        "barely-true": "Misleading",
        "false":       "Fake",
        "pants-fire":  "Fake",
    }
    try:
        logger.info(f"Downloading LIAR TSV from {LIAR_URL}…")
        resp = requests.get(LIAR_URL, timeout=30)
        resp.raise_for_status()
        records = []
        for i, line in enumerate(resp.text.splitlines()):
            if limit and i >= limit:
                break
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            label_raw = parts[1].strip()
            statement = parts[2].strip()
            if len(statement) < 20:
                continue
            records.append({
                "text":   statement,
                "label":  label_map.get(label_raw, "Misleading"),
                "source": "GitHub/LIAR-dataset",
                "topic":  parts[3].strip() if len(parts) > 3 else "news",
            })
        logger.info(f"Loaded {len(records)} records from LIAR TSV ✓")
        return records
    except Exception as e:
        logger.error(f"LIAR manual download failed: {e}")
        return []


# ── GitHub — Additional fake news CSV ──────────────────────────────────────────
def load_github_csv(limit: int | None = None) -> list[dict]:
    """
    Download a public fake-news CSV from GitHub.
    Returns list of {text, label, source} dicts.
    """
    import csv

    for url in [GITHUB_CSV_URL, GITHUB_FALLBACK_URL]:
        try:
            logger.info(f"Downloading GitHub CSV from {url}…")
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            reader = csv.DictReader(io.StringIO(resp.text))
            records = []
            for i, row in enumerate(reader):
                if limit and i >= limit:
                    break
                # Try common column names for text and label
                text = (
                    row.get("statement") or row.get("text") or
                    row.get("title") or row.get("content") or ""
                ).strip()
                label_raw = (
                    row.get("label") or row.get("Label") or
                    row.get("class") or ""
                ).strip().lower()

                if len(text) < 20:
                    continue

                label = "Real"
                if label_raw in ("fake", "0", "false", "pants-fire", "barely-true"):
                    label = "Fake"
                elif label_raw in ("half-true", "misleading", "mixture"):
                    label = "Misleading"
                elif label_raw in ("real", "1", "true", "mostly-true"):
                    label = "Real"

                records.append({
                    "text":   text[:1000],
                    "label":  label,
                    "source": f"GitHub CSV | {url.split('/')[-1]}",
                    "topic":  row.get("subject") or row.get("topic") or "news",
                })

            logger.info(f"Loaded {len(records)} records from GitHub CSV ✓")
            return records

        except Exception as e:
            logger.warning(f"GitHub CSV {url} failed: {e}")
            continue

    logger.warning("All GitHub CSV sources failed — skipping.")
    return []


# ── Upsert to Endee ────────────────────────────────────────────────────────────
def upsert_records(index, records: list[dict]) -> int:
    """Embed and upsert a list of {text, label, source, topic} records."""
    total_upserted = 0
    texts = [r["text"] for r in records]

    logger.info(f"Embedding {len(records)} records…")
    all_embeddings = embed_texts(texts)

    batch = []
    for i, (record, embedding) in enumerate(zip(records, all_embeddings)):
        doc_id = hashlib.md5(record["text"].encode()).hexdigest()
        batch.append({
            "id":     doc_id,
            "vector": embedding,
            "meta": {
                "text":   record["text"][:500],
                "source": record["source"],
                "label":  record["label"],
                "topic":  record.get("topic", "news"),
            },
            "filter": {
                "label": record["label"],
            },
        })

        if len(batch) >= BATCH_SIZE or i == len(records) - 1:
            try:
                index.upsert(batch)
                total_upserted += len(batch)
                logger.info(f"  Upserted batch → {total_upserted}/{len(records)} vectors done")
            except Exception as e:
                logger.error(f"  Upsert batch failed: {e}")
            batch = []
            time.sleep(0.1)  # brief pause between batches

    return total_upserted


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Seed Endee vector DB with fake news data")
    parser.add_argument("--source", choices=["hf", "github", "all"], default="all",
                        help="Data source: hf (HuggingFace), github, or all (default)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max records per source (useful for quick tests)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  Endee Vector DB Seeder — AI Fake News Detector")
    logger.info(f"  Endee URL : {ENDEE_URL}")
    logger.info(f"  Index     : {INDEX_NAME}")
    logger.info(f"  Sources   : {args.source}")
    if args.limit:
        logger.info(f"  Limit     : {args.limit} records per source")
    logger.info("=" * 60)

    # Connect to Endee
    index = get_endee_index()

    total = 0

    # HuggingFace LIAR dataset
    if args.source in ("hf", "all"):
        hf_records = load_huggingface_liar(limit=args.limit)
        if hf_records:
            n = upsert_records(index, hf_records)
            total += n
            logger.info(f"HuggingFace: {n} vectors upserted ✓")

    # GitHub CSV dataset
    if args.source in ("github", "all"):
        gh_records = load_github_csv(limit=args.limit)
        if gh_records:
            n = upsert_records(index, gh_records)
            total += n
            logger.info(f"GitHub CSV: {n} vectors upserted ✓")

    logger.info("=" * 60)
    logger.info(f"✅ Seeding complete! Total vectors upserted: {total}")
    logger.info(f"   Index '{INDEX_NAME}' is ready for RAG queries.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
