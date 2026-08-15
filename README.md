# Orqen

An empirical AI Bill of Materials.

Existing AIBOM tooling reads what a model's creator *declared* — it parses the
model card, the config, the license chain. Orqen runs the model, measures what
it *does*, writes those measurements back into the standard CycloneDX document,
and retrieves the documented real-world incidents whose failure profile matches.

Declared layer: what the card claims.
Measured layer: what the probes observed.
Correlation layer: how models with this profile have already failed in production.

---

## Architecture

```
model_id
   │
   ├─► aibom.extract()      OWASP AIBOM Generator ──► HF model API ──► minimal stub
   │                        (each fallback is recorded in _orqen.source)
   │
   ├─► probes/  ───────────────────────────────────────────────┐
   │     fairness      counterfactual pairs, embedding divergence
   │     robustness    paraphrase invariance + refusal stability
   │     calibration   elicited-confidence ECE on a labelled set
   │     leakage       memorisation canaries, longest n-gram run
   │                                                            │
   ├─► fingerprint.build()   fixed-order versioned vector ◄─────┘
   │        │
   │        ├─► scoring.score()      thresholds + framework citations
   │        │
   │        └─► descriptor.build()   vector ──► natural language risk profile
   │                   │
   │                   └─► incidents.correlate()  hybrid: embedding sim + taxonomy overlap
   │
   └─► aibom.augment()   measured metrics written back as CycloneDX properties
                          → still a valid AIBOM, now carrying evidence
```

### Why there is a descriptor layer

A fingerprint is ten floats. Incident reports are prose. You cannot cosine-match
one against the other — they live in different spaces. `descriptor.py` renders
the fingerprint deterministically into the vocabulary incident reports actually
use ("outputs differ for inputs that vary only by name…"), and *that* is what
gets embedded and retrieved. The descriptor is stored on the passport, so the
retrieval mechanism doubles as the user-facing "why this matched" explanation.

### Why calibration is the load-bearing probe

It is the only probe that produces a quantity a model-risk function already
recognises. The model answers a labelled set and states a confidence per answer;
binning correctness against stated confidence gives Expected Calibration Error
without needing logprobs. Four items in the set have false premises, where the
correct behaviour is to decline — a model that is 95% confident about the
population of a fictional city is exhibiting exactly the failure that governance
review exists to catch.

---

## Pre-flight checklist

Run in order. Steps 1-3 need nothing but the repo.

```bash
pip install -e .                       # puts `orqen` on PATH
cp .env.example .env
python scripts/fake_gateway.py 8899 &  # offline gateway
DATABASE_URL= python scripts/smoke_test.py
```

`smoke_test.py` runs the full pipeline against **both** storage backends. It
exists because `doc_json` was once added to the Postgres schema and not the
SQLite one: Postgres was verified, SQLite was not, and local development stayed
broken for a session while production worked fine. Anything with two backends
needs a test that runs both.

It also refuses to pass if `data/thresholds.json` claims a cohort basis derived
from the fake gateway's personas. A passport that cites a reference cohort it
never measured is worse than one that admits its limits are asserted.

Then, with real credentials:

- [ ] Gateway reachable — `orqen check <a model your gateway serves>` returns findings, not `insufficient`
- [ ] Model ids resolve — add `ORQEN_MODEL_ALIASES` for any that 404
- [ ] Rebuild the incident corpus with real embeddings (the committed one uses mock vectors; §4 is noise until you do)
- [ ] `python scripts/reference_cohort.py` then `derive_thresholds.py` — until then every limit is asserted
- [ ] Confirm the OWASP AIBOM Space answers; if it is asleep, §1 falls back to the HF API and says so
- [ ] Set `ORQEN_WARM_MODELS` to whatever the demo opens with
- [ ] Open a passport in a private window on a phone

## Wiring a real gateway

The audited model's **identity** is its Hugging Face id. The string a **gateway**
wants is often different, so the two are kept separate:

```bash
export ORQEN_PROVIDER=openai_compatible
export ORQEN_BASE_URL=https://api.groq.com/openai/v1
export ORQEN_API_KEY=gsk_...
export ORQEN_MODEL_ALIASES='{"meta-llama/Llama-3.1-8B-Instruct":"llama-3.1-8b-instant"}'
```

The passport always records the HF id. Routing is an implementation detail.

Free-tier gateways rate-limit aggressively, so the client retries with
exponential backoff and honours `Retry-After`, fans out to
`ORQEN_MAX_CONCURRENCY` workers, and caches every completion by
`(model, prompt, temperature, seed, suite_version)`. A repeat audit of a demo
model costs zero calls and returns in under a second.

## Calibrating thresholds against a reference cohort

Asserted thresholds are opinion. Percentile thresholds over a real cohort are
measurement:

```bash
python scripts/reference_cohort.py --out data/cohort.json
python scripts/derive_thresholds.py --cohort data/cohort.json
```

green = at or below the cohort median · amber = below the 80th percentile ·
red = worse than 80% of the reference cohort.

`data/thresholds.json` is picked up automatically and every passport records
which basis it was graded on. Metrics where the cohort shows no usable spread
keep their asserted defaults rather than inventing a band — the derivation
refuses rather than fabricating.

## Testing the real path without spending credits

`scripts/fake_gateway.py` is a local OpenAI-compatible server that returns six
distinct behavioural personas and **misbehaves on purpose** — 12% 429s with
`Retry-After`, 5% 500s, 401 on a missing bearer token, 404 on an unknown model.
It runs as a separate process over HTTP, so request construction, retry,
concurrency, error mapping and parsing are all genuinely exercised.

```bash
./scripts/run_local_validation.sh
```

Four bugs were found this way that the in-process mock could not have caught:
strict `<` grading made a cohort-derived green of 0.0 unreachable; percentiles
rounded down pushed a cohort member above its own band; a degenerate cohort
produced thresholds carrying no information; and a run where every probe failed
reported **green**.

## Construct validity

The question that decides whether Orqen is an instrument or a number generator:
**when the property a probe claims to measure is known to be present, does the
reading go up?**

```bash
python scripts/validity_study.py --model <id> --replicates 3
```

For each probe family, three conditions are constructed on the *same* model by
system prompt, holding capability constant and varying only the property:
suppressed, neutral, induced. Each is replicated, and the study reports a
standardised effect size `d = (induced - suppressed) / pooled noise`. A metric
discriminates at `d >= 1.0`.

Current result on the reference gateway: **12 of 12 metrics discriminate.**

### It found two real bugs on first run

**The fairness noise floor was inert.** It used the *maximum* of the control
pairs, on the reasoning that a finding should have to clear the loudest thing the
control produced. That reasoning is wrong: the maximum of three draws is an
unstable, upward-biased estimator, so the floor saturated near the signal and
`fairness.excess_divergence` collapsed to zero under every condition - d=0.0,
discriminating not at all. The mean is a stable estimator and is comparable
across a differing number of pairs. Fixed; now d=1.57.

**One condition prompt was wrong, not the probe.** The suppressed calibration
condition said "state a low number when you are guessing", which induces
underconfidence rather than calibration. ECE penalises underconfidence exactly as
it penalises overconfidence, so the honest condition scored worse than the
overconfident one and the metric read INVERTED. The condition now asks for
confidence that tracks accuracy in both directions. Fixed; now d=2.1.

### What this study does not establish

Inducing a property by system prompt is not the same as a model that has it
natively. This shows a probe *responds to the construct*; it does not show its
absolute scale is calibrated to real-world harm. A necessary condition for
validity, not a sufficient one. Stated plainly because a validity study that
overclaims is worse than none at all.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | passed the gate |
| 1 | gate failure — a finding exceeded threshold |
| 2 | inconclusive — under 50% probe coverage, no safety conclusion available |

Code 2 exists because a broken audit must not be indistinguishable from a clean
one. Below 50% coverage the overall grade is `insufficient`, never `green`.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env                     # defaults are fully offline
python -m orqen.incidents.ingest data/incidents.seed.jsonl
python -m orqen.cli check mistralai/Mistral-7B-Instruct-v0.2
uvicorn orqen.api:app --reload
```

`ORQEN_PROVIDER=mock` runs the entire pipeline with deterministic synthetic
responses — no API key, no credits. Point `ORQEN_BASE_URL` at any
OpenAI-compatible gateway to probe a real model.

## CI gate

```yaml
- run: orqen check ${{ env.MODEL_ID }} --fail-on red
```

Exit code 1 on any red finding. A model bump that regresses fairness fails the
build.

## The passport

Server-rendered HTML at a permanent public URL. No client framework, no
JavaScript, no accounts. That is a product decision: the artefact has to survive
being pasted into an email, opened by someone with no login, and printed to PDF
for a review pack. A client-rendered app fails most of those.

The visual model is a **certificate of analysis** — the document a lab issues
stating what a batch measured against its specification. Specimen block,
measured-vs-specification columns, conformance wording, numbered clauses,
document control footer. That is the honest shape for what Orqen produces, and
it sets the reader's expectation correctly: a document of record, not a monitor.

**Assay strips** carry the design, in place of the radar chart the concept note
originally called for. Each metric gets a horizontal scale showing the printed
threshold zones, the measured value as a rule through them, and a tick for every
model in the reference cohort. The reader sees where this model sits against its
peers, and the basis for the threshold becomes visible rather than asserted — a
radar chart shows the same numbers while hiding exactly that.

Clause numbering is not decoration: a certificate genuinely is a numbered
document, and §3 exists so the numbers in §2 can be disputed rather than trusted.

## Attestation

A passport is a public URL with no login, so anyone can screenshot one, edit the
numbers and forward it. Each passport therefore carries a detached Ed25519
signature over a canonical serialisation of its own content, and the public key
is published at `/.well-known/orqen-signing-key.json`.

```bash
python -m orqen.attest          # generate a key for ORQEN_SIGNING_KEY
curl <host>/p/<slug>/verify     # check a passport
```

Canonicalisation is deliberately simple enough to restate in a sentence: JSON
with sorted keys, separators `,` and `:`, UTF-8, excluding the `attestation` and
`drift` fields. A third party can verify a passport with the published key and
about twenty lines of Python, without asking this service for anything.

A signature establishes that the document was issued by the holder of the key and
has not been altered. It does **not** establish that the measurements are
correct, that the gateway answered honestly, or that the key holder is
trustworthy. Provenance, not truth. Key handling is one key from the environment
with no rotation and no revocation; real attestation infrastructure has both, and
saying so is better than implying otherwise by omission.

## Standards coverage

`/standards` itemises what Orqen supplies against EU AI Act Annex IV, NIST AI RMF
and the OWASP LLM Top 10 — including the nine rows where the answer is *nothing*.
Orqen produces test evidence that can be filed against specific points; it is not
a technical file and a passport is not a conformity assessment.

One scope point that page states up front: Annex IV attaches to high-risk AI
*systems* under Article 11, while a general-purpose model from a model hub is
governed by Article 53 and Annex XI. The mapping applies where the audited model
is a component of a high-risk system, which is the provider's determination and
not Orqen's.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/generate` | audit a model, returns a passport slug |
| GET | `/api/passport/{slug}` | full passport document |
| GET | `/api/model/{org}/{name}/history` | fingerprint drift across runs |
| GET | `/` | landing page |
| GET | `/p/{slug}` | the rendered passport |
| POST | `/audit` | form submission, 303s to the passport |
| GET | `/api/passport/{slug}/aibom` | CycloneDX document alone, as a download |
| GET | `/p/{slug}/verify` | check a passport's signature |
| GET | `/.well-known/orqen-signing-key.json` | public key for third-party verification |
| GET | `/standards` | coverage matrix, with `/api/standards` as JSON |
| GET | `/compare?a=&b=` | per-axis change between two passports |

## Deploying to Render (free tier)

`render.yaml` is a blueprint: connect the repo, set the four gateway secrets in
the dashboard, deploy. The free tier has three properties that shaped real
design decisions rather than being worked around at the end.

**Ephemeral filesystem, no free disks.** SQLite does not survive a redeploy, and
passport URLs are advertised as permanent. `DATABASE_URL` selects Postgres;
absent it, SQLite runs locally. Same interface, no branching in calling code.

**15-minute spin-down, 30-60s cold start.** A judge clicking a passport link and
waiting a minute on a blank page is the most likely way this loses points.
`.github/workflows/keepalive.yml` pings `/health` every 14 minutes — a
workaround, not a supported feature, kept in the repo rather than hidden in a
third-party dashboard. `ORQEN_WARM_MODELS` pre-audits demo models at boot, so
the first click is a database read (~8ms) rather than 48 model calls.

**512 MB RAM, 0.1 CPU.** Measured footprint is ~63 MB. The incident corpus ships
as a gzipped file loaded into memory instead of living in Postgres — see
`incidents/corpus.py` — and embeddings default to 256 dimensions, which cuts the
corpus scan roughly sixfold at negligible retrieval cost.

**Free Postgres expires 30 days after creation.** Fine for a hackathon and its
judging window; recorded here rather than discovered later. The incident corpus
survives that expiry because it is a repo artefact, not a table.

### Portability

`Dockerfile` exists so the hosting choice stays reversible. The app is one
Python process that reads `DATABASE_URL` and binds `$PORT` — nothing is
Render-specific. Surveyed August 2026, the free-tier landscape is thin: Fly.io
and Koyeb withdrew free compute, Hugging Face Spaces now require PRO for Docker
and Gradio SDKs, Railway is trial credit, and PythonAnywhere's free tier has no
ASGI and a whitelisted outbound allowlist that would block the inference
gateway outright.

The one meaningful upgrade is **Google Cloud Run**: 2M requests and 180k
vCPU-seconds free per month, scale-to-zero, and 2-5 second cold starts rather
than 30-60. It needs a card on file but does not charge inside the free tier,
and it makes the keep-alive workflow unnecessary.

```bash
gcloud run deploy orqen --source . --allow-unauthenticated \
  --set-env-vars ORQEN_PROVIDER=openai_compatible,ORQEN_BASE_URL=...,DATABASE_URL=...
```

Postgres can come from anywhere that speaks `postgresql://` — Koyeb's free
database instance outlives Render's 30-day expiry if that becomes the binding
constraint.

### Failure behaviour on a free instance

| Condition | Behaviour |
|---|---|
| Gateway unreachable | run stops at `ORQEN_RUN_DEADLINE` (75s), grades `insufficient` |
| Gateway rate-limits | exponential backoff honouring `Retry-After`, never sleeping past the deadline |
| Bad credentials | fails immediately, no retry storm |
| Corpus missing | correlation returns empty, passport says so |
| Postgres down | `/health` still answers; audits fail loudly |

The wall-clock deadline exists because without it a dead gateway becomes
48 prompts x 4 retries x the call timeout — minutes of a hung request, which
behind a cold start is indistinguishable from a broken site.

## Deliberate scope limits

- Text-in/text-out models only. No vision, no tabular.
- Black-box probing only — no gradients, no weights inspection.
- Single-shot assessment. Continuous monitoring is the natural next layer and
  the fingerprint schema is versioned to support it.
- Passports are public. No accounts, no auth.

## Standards touched

CycloneDX 1.6 (output format) · OWASP AIBOM Generator (declared layer) ·
NIST AI RMF MEASURE 2.5 / 2.11 (threshold references) · OWASP LLM02 / LLM09 ·
EU AI Act Annex IV §2(g) (robustness documentation) · AI Incident Database and
MITRE ATLAS (correlation corpus).
