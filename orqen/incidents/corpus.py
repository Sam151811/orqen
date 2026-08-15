"""The incident corpus as a build artefact, not runtime state.

Three reasons it stopped being a database table:

  1. Render's free Postgres expires 30 days after creation. An incident corpus
     that dies with the database is a corpus you have to re-embed, and
     re-embedding costs credits at exactly the wrong moment.
  2. pgvector is not guaranteed on the free instance, and a query per request
     at 0.1 CPU is worse than a scan over memory.
  3. Embedding the corpus is deterministic and offline. Anything deterministic
     and offline belongs in the repo, where it is reviewable and versioned.

Vectors are stored truncated to ORQEN_EMBED_DIM (default 256). OpenAI's v3
embeddings are trained so that truncated prefixes remain usable, which cuts the
scan by 6x with little retrieval loss - the difference between ~0.3s and ~2s per
query on a tenth of a CPU.
"""
from __future__ import annotations

import gzip
import json
import math
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                            "data", "incidents.embedded.json.gz")

_cache: dict | None = None


def load(path: str | None = None) -> dict:
    """Loaded once per process at startup. Missing corpus is survivable:
    correlation degrades to empty and the passport says so."""
    global _cache
    if _cache is not None:
        return _cache
    p = path or os.getenv("ORQEN_CORPUS", DEFAULT_PATH)
    try:
        opener = gzip.open if p.endswith(".gz") else open
        with opener(p, "rt") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _cache = {"records": [], "dim": 0, "error": str(exc), "path": p}
        return _cache

    for r in doc.get("records", []):
        r["_norm"] = math.sqrt(sum(x * x for x in r["embedding"])) or 1e-9
    doc["error"] = None
    doc["path"] = p
    _cache = doc
    return _cache


def save(records: list[dict], dim: int, path: str | None = None) -> str:
    p = path or DEFAULT_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with gzip.open(p, "wt") as f:
        json.dump({"dim": dim, "n": len(records), "records": records}, f)
    return p


def stats() -> dict:
    c = load()
    return {"n": len(c.get("records", [])), "dim": c.get("dim", 0),
            "error": c.get("error")}
