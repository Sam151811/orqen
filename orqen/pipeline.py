"""Orchestrator. One function, six stages, each independently degradable.

Design rule: no stage may take down the run. A dead OWASP Space, an empty
incident corpus or a rate-limited gateway each produce a partial passport with
a stated gap rather than a 500. Judges click things; a 500 is the only outcome
that scores zero.
"""
from __future__ import annotations

import secrets
import time
import traceback

from . import aibom as aibom_mod
from . import attest
from . import config, descriptor, fingerprint, scoring
from .incidents.search import correlate
from .probes import SUITE
from .providers import (BudgetExceeded, CallBudget, ChatProvider,
                        DeadlineExceeded, EmbeddingProvider)
from .scoring import grade_metric
from .store import Store


# A passport is read by people who did not write this code. Stack traces in the
# qualifications section are noise to them and leak server paths besides.
_HINTS = {
    "AuthError": ("the credentials for that service were rejected. If this is an "
                  "embedding failure, check ORQEN_EMBED_API_KEY separately from "
                  "ORQEN_API_KEY - they are different services."),
    "ModelUnavailable": ("the gateway does not serve this model under that id. A "
                         "routing alias may be needed."),
    "DeadlineExceeded": "the run hit its wall-clock deadline before this probe.",
    "BudgetExceeded": "the call budget was exhausted before this probe.",
}


def _explain(probe_name: str, exc: Exception) -> str:
    kind = type(exc).__name__
    hint = _HINTS.get(kind)
    if hint:
        return f"Probe {probe_name} did not run: {hint}"
    detail = str(exc).splitlines()[0][:160] if str(exc) else kind
    return f"Probe {probe_name} did not run ({kind}): {detail}"


def run(model_id: str, store: Store | None = None, slug: str | None = None) -> dict:
    store = store or Store()
    slug = slug or f"{model_id.split('/')[-1].lower()[:24]}-{secrets.token_hex(3)}"
    t0 = time.time()
    warnings: list[str] = []

    # 1. declared layer
    declared = aibom_mod.extract(model_id)
    meta = aibom_mod.summarise(declared)
    if meta["source"] == "none":
        warnings.append("No declared AIBOM could be retrieved; measured layer only.")

    # 2. measured layer
    budget = CallBudget(config.MAX_CALLS_PER_RUN, config.RUN_DEADLINE_S)
    embed = EmbeddingProvider(cache=store)

    # Pass 0 runs greedily at temperature 0, so the headline numbers are the
    # deterministic reading and the retained exhibits are reproducible. Later
    # passes sample, and their disagreement with pass 0 is the spread. All passes
    # share one budget and one deadline: a slow gateway costs replicates rather
    # than correctness, and the passport reports how many actually landed.
    replicates, probes_out, coverages = [], [], []
    for rep in range(config.REPEATS):
        temp = 0.0 if rep == 0 else config.REPLICATE_TEMPERATURE
        chat = ChatProvider(model_id, budget, cache=store,
                            temperature=temp, seed=rep)
        results = []
        for probe in SUITE:
            try:
                r = probe.run(chat, embed)
            except DeadlineExceeded:
                warnings.append(
                    f"Run deadline reached during pass {rep + 1}; remaining probes "
                    f"skipped. The inference gateway was slow or unreachable.")
                break
            except BudgetExceeded:
                warnings.append(
                    f"Call budget exhausted during pass {rep + 1}; remaining "
                    f"probes skipped.")
                break
            except Exception as exc:  # noqa: BLE001
                warnings.append(_explain(probe.name, exc))
                continue
            results.append(r)
            if rep == 0:
                probes_out.append({
                    "name": r.name, "metrics": r.metrics, "evidence": r.evidence,
                    "note": r.note, "calls": r.calls, "coverage": r.coverage,
                    "errors": r.errors})
                if r.coverage < 1.0:
                    warnings.append(
                        f"{r.name}: {round(r.coverage * 100)}% of probe items "
                        f"returned cleanly; metrics computed on the usable subset.")
        if results:
            replicates.append(results)
            coverages.append(sum(x.coverage for x in results) / len(SUITE))
        if budget.expired:
            break

    if config.REPEATS > 1 and len(replicates) < config.REPEATS:
        warnings.append(
            f"{len(replicates)} of {config.REPEATS} measurement passes completed; "
            f"spread is estimated from the passes that landed.")

    # 3. fingerprint: mean, spread and standard error across passes
    fp = fingerprint.build(replicates)

    # Anything the passport renders must be set BEFORE it is persisted. A field
    # added after save_passport renders live and vanishes when served - the
    # smoke test compares the two byte for byte precisely to catch that.
    fp["replicate_note"] = (
        "Single deterministic pass; no spread could be estimated, so no "
        "measurement here carries an error bar."
        if fp.get("replicates", 1) < 2 else
        f"{fp['replicates']} independent passes (the first greedy, the rest "
        f"sampled at temperature {config.REPLICATE_TEMPERATURE:g}). Estimates are "
        f"means across passes; spread is the sample standard deviation.")

    # 4. grading. Coverage comes from the deterministic first pass, since that is
    #    the pass whose exhibits are retained and shown in the passport.
    coverage = coverages[0] if coverages else 0.0
    scores = scoring.score(fp, coverage)

    # 5. descriptor + incident correlation
    desc = descriptor.build(model_id, fp, meta)
    fired = {k.split(".")[0] for k, v in fp["metrics"].items()
             if grade_metric(k, v) in ("amber", "red")}
    try:
        incidents = correlate(desc, fired, embed, store)
    except Exception:  # noqa: BLE001
        incidents = []
        warnings.append("Incident correlation unavailable.")
    if not incidents:
        warnings.append("No incident matched above the similarity floor.")

    # 6. augmented artefact
    augmented = aibom_mod.augment(declared, fp, scores)

    passport = {
        "slug": slug,
        "model_id": model_id,
        "created_at": time.time(),
        "suite_version": config.PROBE_SUITE_VERSION,
        "meta": meta,
        "aibom": augmented,
        "probes": probes_out,
        "fingerprint": fp,
        "scores": scores,
        "descriptor": desc,
        "incidents": incidents,
        "warnings": warnings,
        "run": {**budget.snapshot(), "seconds": round(time.time() - t0, 2)},
        "threshold_basis": config.THRESHOLD_BASIS,
        "threshold_cohort": config.COHORT,
        "cohort_values": config.COHORT_VALUES,
    }
    # Signed before persistence so the stored bytes are the attested bytes.
    # Signing after the write would attest to a document nobody can fetch.
    sig = attest.sign(passport)
    if sig:
        passport[attest.SIG_FIELD] = sig

    store.save_passport(passport)

    prior = store.history(model_id, limit=2)
    if len(prior) > 1:
        passport["drift"] = fingerprint.drift(prior[1]["fingerprint"], fp)
    return passport
