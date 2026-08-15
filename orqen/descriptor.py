"""Fingerprint -> natural-language risk descriptor.

The bridge that makes incident retrieval work. A numeric vector cannot be
cosine-matched against text embeddings of incident reports, so the fingerprint
is first rendered deterministically into the vocabulary that incident reports
actually use. The descriptor is stored on the passport and shown to the user as
the 'why this matched' explanation, which turns a retrieval detail into an
interpretability feature.
"""
from __future__ import annotations

from .scoring import grade_metric

PHRASES = {
    "fairness.excess_divergence": (
        "the model produces materially different outputs for otherwise identical "
        "inputs that differ only by name, gender or geography, indicating "
        "demographic bias in an assessment or screening context"),
    "fairness.sentiment_gap": (
        "the model's tone shifts systematically depending on the demographic "
        "identity of the person described"),
    "robustness.paraphrase_variance": (
        "the model returns inconsistent answers to semantically identical "
        "questions, so its output depends on phrasing rather than meaning"),
    "robustness.refusal_instability": (
        "the model's safety refusals can be bypassed by rephrasing the same "
        "request, a prompt-injection and jailbreak exposure"),
    "calibration.ece": (
        "the model's stated confidence does not track its actual accuracy, so "
        "downstream users cannot tell reliable answers from unreliable ones"),
    "calibration.overconfidence": (
        "the model is systematically overconfident and asserts incorrect "
        "information without hedging"),
    "calibration.false_premise_rate": (
        "the model fabricates plausible answers to questions with false premises "
        "instead of declining, a hallucination failure"),
    "leakage.verbatim_rate": (
        "the model reproduces training text verbatim, creating copyright and "
        "sensitive-data disclosure exposure"),
    "leakage.max_run": (
        "the model shows partial memorisation of its training corpus"),
}

CONTEXT = {
    "fairness": "hiring, lending and eligibility decisions",
    "robustness": "customer-facing assistants and automated workflows",
    "calibration": "decision support where a human trusts the model's confidence",
    "leakage": "systems trained on proprietary or personal data",
}


def build(model_id: str, fingerprint: dict, aibom: dict | None = None) -> str:
    flagged = []
    for key, value in fingerprint["metrics"].items():
        g = grade_metric(key, value)
        if g in ("amber", "red") and key in PHRASES:
            flagged.append((g, key))
    flagged.sort(key=lambda x: 0 if x[0] == "red" else 1)

    task = (aibom or {}).get("task", "text generation")
    arch = (aibom or {}).get("architecture", "transformer language model")

    head = (f"A {arch} used for {task}. ")
    if not flagged:
        return head + ("No behavioural risks were measured above threshold. "
                       "Relevant incident classes are those affecting general-purpose "
                       "language models in production deployments.")

    families = {k.split(".")[0] for _, k in flagged}
    body = " ".join(PHRASES[k] for _, k in flagged[:4])
    ctx = "; ".join(CONTEXT[f] for f in sorted(families) if f in CONTEXT)
    return f"{head}Measured failure profile: {body}. Deployment contexts most exposed: {ctx}."
