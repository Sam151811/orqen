"""Standards coverage.

Orqen cites NIST AI RMF and the EU AI Act on every passport. A citation is a
claim, and an unchecked claim is exactly what this project exists to object to.
This module makes the claim checkable: for each requirement, what does Orqen
actually supply, and what must come from somewhere else?

Two framing points that a compliance reader will check first, so they are stated
before any mapping:

1. **Orqen is not a technical file.** Annex IV documentation is a per-system
   dossier prepared by the provider. Orqen produces test evidence that can be
   filed against specific points within it. Nothing here makes a system
   compliant, and a passport is not a conformity assessment.

2. **Annex IV may be the wrong instrument for what Orqen audits.** Annex IV
   attaches to high-risk AI *systems* under Article 11. A general-purpose model
   pulled from a model hub is governed by Article 53 and Annex XI. Orqen audits
   models, so the Annex IV mapping applies when that model is a component of a
   high-risk system - which is the provider's determination, not Orqen's.

Coverage vocabulary, used strictly:

  measured   Orqen produces this by running the model and retains the evidence
  declared   Orqen carries this through from the model's own documentation,
             unverified, and marks it as unverified
  partial    Orqen supplies part of what the point asks for; the remainder is
             named
  external   outside Orqen's scope entirely, with the party who must supply it
"""
from __future__ import annotations

MEASURED, DECLARED, PARTIAL, EXTERNAL = "measured", "declared", "partial", "external"

LEVEL_LABEL = {
    MEASURED: "Measured",
    DECLARED: "Carried through, unverified",
    PARTIAL: "Partially supplied",
    EXTERNAL: "Not supplied",
}

# --- EU AI Act, Annex IV -----------------------------------------------------
# Section titles are paraphrased from Regulation (EU) 2024/1689. They are an
# aid to navigation, not a substitute for the official text, and nothing here
# is legal advice.
ANNEX_IV = [
    ("1", "General description of the system: intended purpose, provider, versions",
     DECLARED,
     "The passport carries the model id, publisher, declared task and licence "
     "from the model's own card into a CycloneDX component, and marks the whole "
     "section unverified. Intended purpose and version history for the enclosing "
     "system must come from the provider."),

    ("2(a-c)", "Development process, design specifications, system architecture",
     EXTERNAL,
     "Requires the provider's own development record. Orqen probes a served "
     "endpoint and inspects no weights, gradients or design artefacts."),

    ("2(d)", "Data governance: training datasets, provenance, labelling, cleaning",
     EXTERNAL,
     "Orqen cannot observe training data. Where a model card discloses it, the "
     "declaration is carried through unverified; where it does not, the gap is "
     "recorded as a gap rather than left blank."),

    ("2(g)", "Validation and testing procedures, metrics for accuracy and robustness, test logs",
     MEASURED,
     "This is the point Orqen is built for. Four probe families with a stated "
     "procedure, fixed prompts, a within-group control condition, replicate "
     "sampling with confidence intervals, and every raw model response retained "
     "as an exhibit so the figures can be re-derived."),

    ("3", "Monitoring, functioning and control of the system in operation",
     PARTIAL,
     "A passport is a single point in time. Repeated audits of the same model "
     "produce a fingerprint history and per-axis drift, which is the input to a "
     "monitoring regime rather than the regime itself. Continuous monitoring, "
     "alerting and human oversight controls are the provider's."),

    ("4", "Appropriateness of the performance metrics used",
     MEASURED,
     "Each metric carries its threshold, the basis for that threshold (asserted "
     "against a published framework, or derived as a percentile of a measured "
     "reference cohort), and a construct-validity effect size showing the metric "
     "responds to the property it claims to measure."),

    ("5", "Risk management system",
     EXTERNAL,
     "An organisational process under Article 9. Orqen output is an input to it."),

    ("6", "Changes made to the system through its lifecycle",
     PARTIAL,
     "Fingerprints are versioned and comparable across runs, so a change in "
     "measured behaviour between two dates is evidence of a lifecycle change. "
     "Orqen sees behaviour, not the change itself or its cause."),

    ("7", "Harmonised standards applied",
     DECLARED,
     "The passport names the standards its own output conforms to. The list for "
     "the enclosing system is the provider's."),

    ("8", "EU declaration of conformity",
     EXTERNAL,
     "A provider's signed legal declaration. Orqen issues test evidence and is "
     "explicit that a passing determination is not a conformity assessment."),

    ("9", "Post-market monitoring plan",
     EXTERNAL,
     "A plan document under Article 72. Orqen's re-audit and drift capability "
     "could be an instrument named within such a plan."),
]

# --- NIST AI RMF -------------------------------------------------------------
NIST_RMF = [
    ("MEASURE 2.5", "Validity and reliability of the system are demonstrated",
     MEASURED,
     "Elicited-confidence calibration on a labelled set including false-premise "
     "items, reported as expected calibration error with an interval."),
    ("MEASURE 2.7", "Security and resilience are evaluated",
     PARTIAL,
     "Refusal stability under paraphrase is measured. Adversarial robustness, "
     "supply-chain and infrastructure security are not in scope."),
    ("MEASURE 2.9", "Model output is explainable and interpretable",
     PARTIAL,
     "Every measurement links to the raw responses behind it, and the incident "
     "descriptor is generated deterministically from the measured vector. Orqen "
     "does not explain the model's internals."),
    ("MEASURE 2.10", "Privacy risk is evaluated",
     PARTIAL,
     "Memorisation canaries detect verbatim reproduction of public training "
     "text. Membership inference and PII extraction are not implemented."),
    ("MEASURE 2.11", "Fairness and bias are evaluated",
     MEASURED,
     "Counterfactual pairs across name, pronoun, geography and age, net of a "
     "within-group control condition that establishes the noise floor."),
    ("MEASURE 4.2", "Measurement results are documented and reviewable",
     MEASURED,
     "The passport is a permanent public URL carrying the method, the thresholds "
     "and their basis, coverage, qualifications and the raw exhibits."),
    ("GOVERN 1.2", "Trustworthy AI characteristics are integrated into policy",
     EXTERNAL,
     "Organisational. Orqen produces evidence such a policy could require."),
]

# --- OWASP LLM Top 10 --------------------------------------------------------
OWASP_LLM = [
    ("LLM02", "Sensitive information disclosure", MEASURED,
     "Memorisation canaries measure verbatim reproduction of known public text."),
    ("LLM09", "Overreliance", MEASURED,
     "Calibration error and false-premise fabrication rate both quantify the "
     "gap between stated confidence and actual accuracy."),
    ("LLM01", "Prompt injection", PARTIAL,
     "Refusal instability under rephrasing is a proxy for susceptibility. "
     "Indirect injection through retrieved content is not tested."),
    ("LLM04", "Data and model poisoning", EXTERNAL,
     "Requires training-pipeline visibility Orqen does not have."),
    ("LLM10", "Unbounded consumption", EXTERNAL,
     "A deployment-layer control, not a model property."),
]

FRAMEWORKS = [
    ("EU AI Act, Annex IV", "Technical documentation, Article 11", ANNEX_IV,
     "Applies to high-risk AI systems. A general-purpose model is governed by "
     "Article 53 and Annex XI; this mapping applies where the audited model is a "
     "component of a high-risk system, which is the provider's determination."),
    ("NIST AI RMF 1.0", "Measure and Govern functions", NIST_RMF, ""),
    ("OWASP Top 10 for LLM Applications", "", OWASP_LLM, ""),
]


def summary() -> dict:
    """Counts per level, for the headline line. Deliberately reports the
    not-supplied count first: the honest headline is what is missing."""
    out = {}
    for name, _sub, rows, _note in FRAMEWORKS:
        counts = {MEASURED: 0, DECLARED: 0, PARTIAL: 0, EXTERNAL: 0}
        for _ref, _title, level, _note2 in rows:
            counts[level] += 1
        out[name] = {"total": len(rows), **counts}
    return out


def headline() -> str:
    s = summary()["EU AI Act, Annex IV"]
    supplied = s[MEASURED] + s[PARTIAL]
    return (f"Orqen supplies evidence toward {supplied} of {s['total']} Annex IV "
            f"points and none of the remaining {s[EXTERNAL] + s[DECLARED]}. "
            f"It is test evidence for a technical file, not a technical file, "
            f"and not a conformity assessment.")
