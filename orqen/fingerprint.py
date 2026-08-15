"""The fingerprint: a fixed-length, fixed-order, versioned vector of measured
behaviour. Fixed order is what makes two models comparable and what makes drift
across re-runs meaningful. Adding a metric bumps the version rather than
silently shifting positions.
"""
from __future__ import annotations

import hashlib
import statistics

SCHEMA: tuple[str, ...] = (
    "fairness.excess_divergence",
    "fairness.control_divergence",
    "fairness.max_pair_divergence",
    "fairness.sentiment_gap",
    "robustness.paraphrase_variance",
    "robustness.refusal_instability",
    "calibration.ece",
    "calibration.overconfidence",
    "calibration.accuracy",
    "calibration.false_premise_rate",
    "leakage.verbatim_rate",
    "leakage.max_run",
)


def build(replicates) -> dict:
    """replicates: a list of probe-result lists, one per independent pass.

    With one pass this behaves exactly as before. With several it reports the
    mean as the estimate, the sample standard deviation as the spread, and the
    standard error, so downstream grading can ask whether an estimate is
    actually distinguishable from its threshold.
    """
    if replicates and not isinstance(replicates[0], list):
        replicates = [replicates]          # tolerate a bare result list

    samples: dict[str, list[float]] = {k: [] for k in SCHEMA}
    for run_results in replicates:
        seen: dict[str, float] = {}
        for pr in run_results:
            seen.update(pr.metrics)
        for k in SCHEMA:
            if k in seen:
                samples[k].append(float(seen[k]))

    vector, spread, stderr, counts = [], [], [], []
    for k in SCHEMA:
        vals = samples[k]
        n = len(vals)
        mean = sum(vals) / n if n else 0.0
        sd = statistics.stdev(vals) if n > 1 else 0.0
        vector.append(round(mean, 6))
        spread.append(round(sd, 6))
        stderr.append(round(sd / (n ** 0.5), 6) if n > 1 else 0.0)
        counts.append(n)

    # The digest identifies the measured behaviour, so it is built from the
    # estimates only. Two runs that agree within noise get the same digest only
    # if their means round identically - which is the intended behaviour: the
    # digest is an identity, not a certificate of stability.
    digest = hashlib.sha256(
        "|".join(f"{k}={v:.4f}" for k, v in zip(SCHEMA, vector)).encode()
    ).hexdigest()[:16]

    return {
        "schema": list(SCHEMA),
        "vector": vector,
        "digest": digest,
        "replicates": len(replicates),
        "metrics": {k: v for k, v in zip(SCHEMA, vector)},
        "spread": {k: v for k, v in zip(SCHEMA, spread)},
        "stderr": {k: v for k, v in zip(SCHEMA, stderr)},
        "n": {k: v for k, v in zip(SCHEMA, counts)},
    }


def drift(a: dict, b: dict) -> dict:
    """Per-axis delta between two runs. Powers 'this model got worse' in the UI."""
    if a["schema"] != b["schema"]:
        return {"comparable": False}
    deltas = {k: round(y - x, 6)
              for k, x, y in zip(a["schema"], a["vector"], b["vector"])}
    worst = max(deltas.items(), key=lambda kv: kv[1])
    return {"comparable": True, "deltas": deltas,
            "largest_regression": {"metric": worst[0], "delta": worst[1]}}
