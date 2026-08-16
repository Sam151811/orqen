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

# 0.20 was asserted, and it was unreachable: no two records in the shipped
# corpus score above 0.18, so nothing could ever clear it. The default below is
# the 95th percentile of the null distribution - every pair of incidents sharing
# no taxonomy tag - which fixes the false-positive rate by construction at
# roughly one unrelated incident in twenty.
#
# Caveat that belongs next to the number: on this corpus the related and
# unrelated distributions overlap almost completely, so a cleared floor is
# suggestive, not probative. Widening the corpus is what would make correlation
# load-bearing.
SIM_FLOOR = float(os.getenv("ORQEN_SIM_FLOOR", "0.0719"))


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
    # An empty result is a finding, not a gap in the page. Returning the nearest
    # neighbour when nothing clears the floor manufactures a correlation the
    # measurement does not support: with a small corpus something is always
    # nearest, so a panel that can never be empty carries no information.
    top = [m for m in scored if m["similarity"] >= SIM_FLOOR][:top_k]
    for m in top:
        m["confidence"] = "strong" if m["matched_tags"] else "moderate"
        m["why"] = _why(m, fired_families)
    return top


def _why(match: dict, families: set[str]) -> str:
    if match["matched_tags"]:
        return (f"Shares failure class ({', '.join(match['matched_tags'])}) with the "
                f"{', '.join(sorted(families))} risks measured on this model.")
    return ("Cleared the similarity floor on descriptor text alone, with no "
            "taxonomy overlap. Suggestive of a shared failure mode rather than "
            "evidence of one.")
