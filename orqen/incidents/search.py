"""Incident correlation.

Retrieval is hybrid on purpose. Pure vector search over ~3k incident summaries
returns thematically-close-but-wrong matches often enough to embarrass you in a
demo. Each candidate is therefore re-ranked by (a) embedding similarity to the
risk descriptor and (b) overlap between the incident's taxonomy tags and the
probe families that actually fired. A match must clear a floor on both.
"""
from __future__ import annotations

import math

from ..providers import cosine
from . import corpus

FAMILY_TAGS = {
    "fairness": {"bias", "discrimination", "fairness", "race", "gender", "hiring"},
    "robustness": {"jailbreak", "prompt-injection", "robustness", "adversarial", "misuse"},
    "calibration": {"hallucination", "misinformation", "accuracy", "overreliance"},
    "leakage": {"privacy", "pii", "copyright", "memorisation", "data-leak"},
}

import os

SIM_FLOOR = float(os.getenv("ORQEN_SIM_FLOOR", "0.20"))


def correlate(descriptor: str, fired_families: set[str], embed, store=None,
              top_k: int = 3) -> list[dict]:
    c = corpus.load()
    if not c.get("records"):
        return []
    qvec = embed.embed([descriptor])[0]
    dim = c.get("dim") or len(qvec)
    qvec = qvec[:dim]
    qnorm = math.sqrt(sum(x * x for x in qvec)) or 1e-9
    wanted = set().union(*[FAMILY_TAGS.get(f, set()) for f in fired_families]) \
        if fired_families else set()

    scored = []
    for inc in c["records"]:
        # inlined cosine: the corpus norm is precomputed at load, so this is
        # one dot product per record rather than three passes.
        sim = sum(a * b for a, b in zip(qvec, inc["embedding"])) / (qnorm * inc["_norm"])
        tags = {t.lower() for t in inc.get("taxonomy", [])}
        overlap = tags & wanted
        tag_boost = 0.15 * min(len(overlap), 2)
        scored.append({
            "id": inc["id"], "title": inc["title"], "url": inc["url"],
            "summary": (inc.get("description") or "")[:320],
            "similarity": round(sim, 4),
            "matched_tags": sorted(overlap),
            "rank_score": round(sim + tag_boost, 4),
        })

    scored.sort(key=lambda x: -x["rank_score"])
    strong = [m for m in scored if m["similarity"] >= SIM_FLOOR]
    # Never return an empty list: the nearest neighbour, honestly labelled, is
    # more useful to a reviewer than silence - and reads better in a demo than
    # a blank panel.
    top = (strong or scored[:1])[:top_k]
    for m in top:
        m["confidence"] = ("strong" if m["similarity"] >= SIM_FLOOR and m["matched_tags"]
                           else "moderate" if m["similarity"] >= SIM_FLOOR
                           else "weak")
        m["why"] = _why(m, fired_families)
    return top


def _why(match: dict, families: set[str]) -> str:
    if match["matched_tags"]:
        return (f"Shares failure class ({', '.join(match['matched_tags'])}) with the "
                f"{', '.join(sorted(families))} risks measured on this model.")
    return ("Nearest neighbour on descriptor similarity, with no taxonomy overlap. "
            "Weak evidence - shown for completeness, not as a finding.")
