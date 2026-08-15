"""HTTP surface.

The passport is server-rendered HTML at a permanent public URL. That is a
deliberate product decision, not a shortcut: the artefact has to survive being
pasted into an email, opened by someone with no account, printed to PDF and
attached to a review pack. A client-rendered app fails most of those.
"""
from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (HTMLResponse, JSONResponse, RedirectResponse,
                               Response)
from pydantic import BaseModel

from . import attest, config, standards
from .incidents import corpus
from .pipeline import run
from .providers import AuthError, ModelUnavailable, ProviderError
from .render import compare_html, passport_html, standards_html
from .ui import (FAVICON, MANIFEST, error_html, fleet_html, fleet_stats,
                 landing_html)
from .store import open_store

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Boot work happens once, not per request.

    On a free instance every request may follow a 60-second cold start, so the
    corpus is loaded and demo models are pre-audited here. A judge's first click
    then reads a row instead of running 48 model calls.
    """
    corpus.load()
    store = open_store()
    for model_id in config.WARM_MODELS:
        try:
            if not store.history(model_id, limit=1):
                run(model_id, store=store)
        except Exception:  # noqa: BLE001 - warming must never block boot
            pass
    yield


app = FastAPI(title="Orqen", version="0.1.0", docs_url="/api/docs",
              lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

MODEL_ID = re.compile(r"^[A-Za-z0-9._\-]+/[A-Za-z0-9._\-]+$")

# --- rate limiting -----------------------------------------------------------
# A public audit endpoint spends the operator's gateway credits, not the
# caller's. Without a limit, one person in a loop drains the quota and every
# later visitor gets an inconclusive passport. Reads are unlimited: serving a
# stored passport costs a database round trip.
#
# In-memory and per-process on purpose. The free tier runs a single worker, and
# a shared counter in Postgres would add a write to every request to defend
# against a threat this size.
AUDIT_LIMIT = int(os.getenv("ORQEN_AUDIT_LIMIT", "6"))
AUDIT_WINDOW_S = float(os.getenv("ORQEN_AUDIT_WINDOW", "3600"))
GLOBAL_LIMIT = int(os.getenv("ORQEN_GLOBAL_AUDIT_LIMIT", "60"))

_hits: dict[str, deque] = {}
_global: deque = deque()
_rl_lock = threading.Lock()


def _client_key(request: Request) -> str:
    # Render terminates TLS upstream, so the caller's address arrives in
    # X-Forwarded-For. Falling back to the socket address would bucket every
    # visitor together behind the proxy.
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_check(key: str) -> tuple[bool, str]:
    now = time.monotonic()
    with _rl_lock:
        for q in (_hits.setdefault(key, deque()), _global):
            while q and now - q[0] > AUDIT_WINDOW_S:
                q.popleft()
        if len(_hits[key]) >= AUDIT_LIMIT:
            wait = int((AUDIT_WINDOW_S - (now - _hits[key][0])) / 60) + 1
            return False, (f"This address has issued {AUDIT_LIMIT} passports in the "
                           f"last hour, which is the limit. Try again in about "
                           f"{wait} minutes. Existing passports stay readable.")
        if len(_global) >= GLOBAL_LIMIT:
            return False, ("Orqen is at its hourly audit ceiling across all "
                           "callers. This protects the gateway quota so passports "
                           "stay accurate. Existing passports stay readable.")
        _hits[key].append(now)
        _global.append(now)
        if len(_hits) > 2000:          # bound the dict, drop idle buckets
            for k in [k for k, v in _hits.items() if not v][:1000]:
                _hits.pop(k, None)
        return True, ""


class GenerateRequest(BaseModel):
    model_id: str


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _audit(model_id: str):
    """Shared by the form, the GET shortcut and the JSON API. Returns
    (slug, error_message)."""
    if not MODEL_ID.match(model_id or ""):
        return None, "A model id looks like org/model, for example meta-llama/Llama-3.1-8B-Instruct."
    try:
        p = run(model_id, store=open_store())
    except AuthError:
        return None, "The configured inference gateway rejected our credentials. Nothing was measured."
    except ModelUnavailable:
        return None, f"The gateway does not serve {model_id}. Check the id, or add a routing alias."
    except ProviderError as exc:
        return None, f"The inference gateway was unreachable: {exc}"
    return p, None


# --- HTML --------------------------------------------------------------------
RANGES = [("24H", "24h"), ("7D", "7d"), ("30D", "30d"), ("ALL", "All")]
RANGE_SECONDS = {"24H": 86400, "7D": 604800, "30D": 2592000}
RANGE_LABEL = {"24H": "Last 24 hours", "7D": "Last 7 days",
               "30D": "Last 30 days", "ALL": "All time"}


def _estate() -> dict:
    """Cheap enough to run on every landing render, and it fails soft: a
    database hiccup should cost the counters, not the page."""
    try:
        rows = open_store().list_passports(limit=300)
        st = fleet_stats(rows)
        return {"models": st["models"], "passports": st["passports"],
                "suite": config.PROBE_SUITE_VERSION}
    except Exception:  # noqa: BLE001
        return {"suite": config.PROBE_SUITE_VERSION}


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(landing_html(stats=_estate()))


@app.get("/fleet", response_class=HTMLResponse)
def fleet(range: str = "ALL"):
    """The index that did not exist: until now a passport was unreachable unless
    you already knew its slug."""
    key = range if range in RANGE_LABEL else "ALL"
    since = (time.time() - RANGE_SECONDS[key]) if key in RANGE_SECONDS else None
    rows = open_store().list_passports(limit=300, since=since)
    return HTMLResponse(fleet_html(rows, RANGE_LABEL[key], RANGES, key))


@app.get("/api/fleet")
def fleet_json(range: str = "ALL"):
    key = range if range in RANGE_LABEL else "ALL"
    since = (time.time() - RANGE_SECONDS[key]) if key in RANGE_SECONDS else None
    rows = open_store().list_passports(limit=300, since=since)
    st = fleet_stats(rows)
    return {"range": key, "models": st["models"], "passports": st["passports"],
            "mean_coverage": round(st["mean_coverage"], 4),
            "with_red": st["with_red"],
            "entries": [{"slug": m["slug"], "model_id": m["model_id"],
                         "created_at": m["created_at"],
                         "overall": (m.get("scores") or {}).get("overall"),
                         "coverage": (m.get("scores") or {}).get("coverage"),
                         "digest": (m.get("fingerprint") or {}).get("digest")}
                        for m in st["latest"]]}


@app.get("/favicon.svg")
def favicon():
    return Response(FAVICON, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/site.webmanifest")
def manifest():
    return JSONResponse(MANIFEST, media_type="application/manifest+json")


@app.post("/audit")
def audit_form(request: Request, model_id: str = Form(...)):
    ok, msg = _rate_check(_client_key(request))
    if not ok:
        return HTMLResponse(landing_html(error=msg, stats=_estate()), status_code=429)
    p, err = _audit(model_id.strip())
    if err:
        return HTMLResponse(landing_html(error=err, stats=_estate()), status_code=400)
    return RedirectResponse(f"/p/{p['slug']}", status_code=303)


@app.get("/audit")
def audit_link(request: Request, model_id: str = ""):
    ok, msg = _rate_check(_client_key(request))
    if not ok:
        return HTMLResponse(landing_html(error=msg, stats=_estate()), status_code=429)
    p, err = _audit(model_id.strip())
    if err:
        return HTMLResponse(landing_html(error=err, stats=_estate()), status_code=400)
    return RedirectResponse(f"/p/{p['slug']}", status_code=303)


@app.get("/p/{slug}", response_class=HTMLResponse)
def passport_page(slug: str, request: Request):
    p = open_store().get_passport(slug)
    if not p:
        return HTMLResponse(
            error_html(404, "No passport was issued under that reference. "
                            "Passports are permanent, so this id was never valid."),
            status_code=404)
    return HTMLResponse(passport_html(p, _base(request)))


@app.get("/standards", response_class=HTMLResponse)
def standards_page():
    """What Orqen supplies against each framework it cites, and what it does
    not. Public because an unchecked citation is exactly what this project
    objects to."""
    return HTMLResponse(standards_html())


@app.get("/compare", response_class=HTMLResponse)
def compare_page(a: str = "", b: str = ""):
    store = open_store()
    pa, pb = store.get_passport(a), store.get_passport(b)
    if not pa or not pb:
        missing = a if not pa else b
        return HTMLResponse(
            error_html(404, f"No passport was issued under the reference "
                            f"'{missing}'. Comparison needs two valid references, "
                            f"as /compare?a=<slug>&b=<slug>."),
            status_code=404)
    return HTMLResponse(compare_html(pa, pb))


@app.get("/p/{slug}/verify", response_class=HTMLResponse)
def verify_page(slug: str, request: Request):
    p = open_store().get_passport(slug)
    if not p:
        return HTMLResponse(error_html(404, "No passport under that reference."),
                            status_code=404)
    return JSONResponse(attest.verify(p))


@app.get("/.well-known/orqen-signing-key.json")
def signing_key():
    """Published so a third party can verify a passport without asking Orqen
    for anything but this key."""
    pk = attest.public_key_b64()
    if not pk:
        return JSONResponse({"error": "this instance is not signing passports"},
                            status_code=503)
    return {"alg": attest.ALG, "key_id": attest.key_id(), "public_key": pk,
            "ephemeral": attest._ephemeral,
            "canonicalisation": ("JSON with sorted keys, separators ',' and ':', "
                                 "UTF-8, excluding the attestation and drift "
                                 "fields, then Ed25519 over those bytes")}


@app.get("/api/standards")
def standards_json():
    return {"headline": standards.headline(), "summary": standards.summary(),
            "frameworks": [
                {"name": n, "subtitle": sub, "note": note,
                 "rows": [{"ref": r, "requirement": t, "coverage": lvl,
                           "detail": d} for r, t, lvl, d in rows]}
                for n, sub, rows, note in standards.FRAMEWORKS]}


# --- JSON --------------------------------------------------------------------
@app.get("/health")
def health():
    """Cheap by design - the keep-alive workflow hits this every 14 minutes and
    must not cost a database round trip or a model call."""
    c = corpus.stats()
    with _rl_lock:
        recent = len(_global)
    return {"ok": True, "corpus": c["n"], "corpus_error": c["error"],
            "store": open_store().backend, "suite": config.PROBE_SUITE_VERSION,
            "audits_last_hour": recent, "audit_ceiling": GLOBAL_LIMIT}


@app.post("/api/generate")
def generate(req: GenerateRequest, request: Request):
    ok, msg = _rate_check(_client_key(request))
    if not ok:
        return JSONResponse({"error": msg}, status_code=429)
    p, err = _audit(req.model_id)
    if err:
        return JSONResponse({"error": err}, status_code=400)
    return {"slug": p["slug"], "overall": p["scores"]["overall"],
            "digest": p["fingerprint"]["digest"],
            "passport_url": f"/p/{p['slug']}"}


@app.get("/api/passport/{slug}")
def passport_json(slug: str):
    p = open_store().get_passport(slug)
    if not p:
        return JSONResponse({"error": "no passport with that reference"}, status_code=404)
    return p


@app.get("/api/passport/{slug}/aibom")
def passport_aibom(slug: str):
    """The CycloneDX document alone, for anything that consumes AIBOMs."""
    p = open_store().get_passport(slug)
    if not p:
        return JSONResponse({"error": "no passport with that reference"}, status_code=404)
    return JSONResponse(p["aibom"], headers={
        "Content-Disposition": f'attachment; filename="{slug}.cdx.json"'})


@app.get("/api/model/{org}/{name}/history")
def history(org: str, name: str):
    return {"model_id": f"{org}/{name}", "runs": open_store().history(f"{org}/{name}")}
