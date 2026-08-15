"""Build the shipped incident corpus. Run offline, commit the output.

Reads newline-delimited JSON (the AI Incident Database publishes a full export;
MITRE ATLAS case studies append in the same shape), embeds title + description,
truncates to ORQEN_EMBED_DIM and writes data/incidents.embedded.json.gz.

  {"id": "...", "title": "...", "description": "...", "url": "...",
   "taxonomy": ["bias", "hiring"]}
"""
from __future__ import annotations

import json
import sys

from .. import config
from ..providers import EmbeddingProvider
from ..store import Store
from . import corpus

BATCH = 64


def ingest(path: str, out: str | None = None) -> int:
    embed = EmbeddingProvider(cache=Store())   # cache so re-runs are free
    raw, records = [], []

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            raw.append({
                "id": str(rec.get("id") or rec.get("incident_id")),
                "title": rec.get("title", ""),
                "description": rec.get("description") or rec.get("summary") or "",
                "url": rec.get("url") or rec.get("report_url") or "",
                "taxonomy": rec.get("taxonomy") or rec.get("tags") or [],
            })

    dim = config.EMBED_DIM
    for i in range(0, len(raw), BATCH):
        chunk = raw[i:i + BATCH]
        vecs = embed.embed([f"{r['title']}. {r['description']}"[:2000] for r in chunk])
        for r, v in zip(chunk, vecs):
            records.append({**r, "embedding": [round(x, 6) for x in v[:dim]]})
        print(f"  embedded {len(records)}/{len(raw)}", file=sys.stderr)

    real_dim = len(records[0]["embedding"]) if records else 0
    p = corpus.save(records, real_dim, out)
    print(f"wrote {p}: {len(records)} incidents at dim {real_dim}")
    return len(records)


if __name__ == "__main__":
    ingest(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
