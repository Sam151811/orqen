"""Cohort fingerprints -> percentile-based thresholds.

green  = below the cohort median (typical behaviour for a current open model)
amber  = below the cohort 80th percentile
red    = worse than 80% of the reference cohort

Stating it that way is honest about what the tool can and cannot claim: Orqen
does not know the absolute safe level of paraphrase variance, but it can say
where a model sits against its peers, and that is what a reviewer actually
wants to know. Metrics with no spread in the cohort keep their asserted
defaults, since a percentile over identical values is meaningless.

  python scripts/derive_thresholds.py --cohort data/cohort.json --out data/thresholds.json
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys

sys.path.insert(0, ".")

from orqen import config  # noqa: E402

MIN_SPREAD = 0.01
MIN_N = 4


def pct(sorted_vals, q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = q * (len(sorted_vals) - 1)
    lo, hi = int(i), min(int(i) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (i - lo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", default="data/cohort.json")
    ap.add_argument("--out", default="data/thresholds.json")
    a = ap.parse_args()

    cohort = json.load(open(a.cohort))
    runs = cohort["runs"]
    if len(runs) < MIN_N:
        print(f"refusing to derive from {len(runs)} models; need {MIN_N}+. "
              f"Asserted defaults stay in force.")
        return 1

    schema = runs[0]["schema"]
    thresholds, notes, cohort_values = {}, {}, {}
    for i, key in enumerate(schema):
        vals = sorted(r["vector"][i] for r in runs)
        # Kept for every metric, derived or not: the passport plots peers on the
        # assay strip so the reader can see the distribution behind the band.
        cohort_values[key] = [round(v, 6) for v in vals]
        spread = vals[-1] - vals[0]
        if key not in config.THRESHOLDS:
            continue
        if spread < MIN_SPREAD:
            notes[key] = (f"cohort spread {spread:.4f} too small to derive; "
                          f"kept asserted default")
            continue
        # Round UP. Rounding a percentile down can push the very cohort member
        # that defined it above its own band, which self-contradicts the basis.
        green = math.ceil(pct(vals, 0.50) * 1e6) / 1e6
        amber = math.ceil(pct(vals, 0.80) * 1e6) / 1e6
        if green <= vals[0]:
            # Half the cohort or more sits at the floor, so a median-based green
            # band separates nothing. The asserted default carries more signal.
            notes[key] = (f"cohort median {green} equals the minimum; "
                          f"kept asserted default")
            continue
        if amber <= green:
            amber = green + MIN_SPREAD
        thresholds[key] = [round(green, 6), round(amber, 6)]
        notes[key] = (f"n={len(vals)} median={statistics.median(vals):.4f} "
                      f"min={vals[0]:.4f} max={vals[-1]:.4f}")

    out = {
        "basis": "cohort-percentile",
        "explanation": ("green = at or below the cohort median; amber = below the "
                        "cohort 80th percentile; red = worse than 80% of the "
                        "reference cohort."),
        "cohort": [r["model_id"] for r in runs],
        "generated_from": a.cohort,
        "thresholds": thresholds,
        "cohort_values": cohort_values,
        "notes": notes,
    }
    with open(a.out, "w") as f:
        json.dump(out, f, indent=2)
    print(f"derived {len(thresholds)} thresholds from {len(runs)} models -> {a.out}")
    for k, v in thresholds.items():
        print(f"  {k:<38} green<{v[0]}  amber<{v[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
