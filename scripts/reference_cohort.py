"""Run the probe suite across a cohort of models and write the raw fingerprints.

This is what converts Orqen's thresholds from opinion into measurement. Without
a cohort, "green is below 0.10" is a number someone chose. With one, it becomes
"green is below the cohort median", which is defensible under questioning.

  python scripts/reference_cohort.py --models models.txt --out data/cohort.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

sys.path.insert(0, ".")

from orqen.pipeline import run          # noqa: E402
from orqen.store import Store           # noqa: E402

DEFAULT = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "Qwen/Qwen2.5-7B-Instruct",
    "google/gemma-2-9b-it",
    "microsoft/Phi-3.5-mini-instruct",
    "HuggingFaceH4/zephyr-7b-beta",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", help="file with one model id per line")
    ap.add_argument("--out", default="data/cohort.json")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()

    models = DEFAULT
    if a.models:
        models = [l.strip() for l in open(a.models) if l.strip()
                  and not l.startswith("#")]

    store = Store(a.db)
    rows, failed = [], []
    for m in models:
        t = time.time()
        print(f"  probing {m} ... ", end="", flush=True)
        try:
            p = run(m, store=store)
        except Exception:
            failed.append({"model_id": m, "error": traceback.format_exc(limit=2)})
            print("FAILED")
            continue
        cov = {pr["name"]: round(pr.get("coverage", 1.0), 3) for pr in p["probes"]}
        rows.append({
            "model_id": m,
            "slug": p["slug"],
            "digest": p["fingerprint"]["digest"],
            "schema": p["fingerprint"]["schema"],
            "vector": p["fingerprint"]["vector"],
            "coverage": cov,
            "calls": p["run"]["calls"],
            "seconds": round(time.time() - t, 1),
        })
        print(f"{p['fingerprint']['digest']}  {p['run']['calls']} calls  "
              f"{time.time() - t:.1f}s  cov={min(cov.values()) if cov else 0}")

    out = {"generated_at": time.time(), "n": len(rows),
           "runs": rows, "failed": failed}
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nwrote {a.out}: {len(rows)} succeeded, {len(failed)} failed")
    return 0 if rows else 1


if __name__ == "__main__":
    sys.exit(main())
