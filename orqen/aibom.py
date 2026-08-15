"""Declared-layer extraction, then augmentation.

Orqen does not reimplement AIBOM generation - it calls the OWASP AIBOM
Generator, and falls back to the Hugging Face model API if that Space is asleep
(Spaces cold-start in ~30s, which is a demo-killer, so the fallback is not
optional). The interesting part is augment(): measured probe results are written
back onto the CycloneDX component as evidence properties, so the artefact that
leaves Orqen is a standard-shaped AIBOM that additionally carries what the model
was observed to do, not only what its card claims.
"""
from __future__ import annotations

import json
import urllib.request

from . import config

OWASP_ENDPOINT = "https://aetheris-ai-aibom-generator.hf.space/api/generate"
HF_API = "https://huggingface.co/api/models/"
NS = "orqen:measured:"


def _get(url: str, timeout: float = 12.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "orqen/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _post(url: str, payload: dict, timeout: float = 25.0) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _minimal(model_id: str, meta: dict | None = None) -> dict:
    meta = meta or {}
    tags = meta.get("tags", [])
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "metadata": {"component": {"type": "machine-learning-model", "name": model_id}},
        "components": [{
            "type": "machine-learning-model",
            "name": model_id.split("/")[-1],
            "group": model_id.split("/")[0] if "/" in model_id else "",
            "publisher": meta.get("author", ""),
            "licenses": [{"license": {"id": t.split(":")[1]}}
                         for t in tags if t.startswith("license:")],
            "properties": [{"name": "hf:pipeline_tag",
                            "value": meta.get("pipeline_tag", "text-generation")},
                           {"name": "hf:downloads", "value": str(meta.get("downloads", ""))}],
        }],
        "_orqen": {"source": "fallback"},
    }


def extract(model_id: str) -> dict:
    """Best-effort declared AIBOM. Never raises - a missing declared layer is a
    finding in itself, not a crash."""
    try:
        doc = _post(OWASP_ENDPOINT, {"model_id": model_id})
        if isinstance(doc, dict) and doc.get("bomFormat"):
            doc["_orqen"] = {"source": "owasp-aibom-generator"}
            return doc
        if isinstance(doc, dict) and isinstance(doc.get("aibom"), dict):
            inner = doc["aibom"]
            inner["_orqen"] = {"source": "owasp-aibom-generator",
                               "completeness": doc.get("completeness_score")}
            return inner
    except Exception as e:  # noqa: BLE001
        last = str(e)
    else:
        last = "unexpected response shape"

    try:
        meta = _get(HF_API + model_id)
        doc = _minimal(model_id, meta)
        doc["_orqen"] = {"source": "huggingface-api", "owasp_error": last}
        return doc
    except Exception as e:  # noqa: BLE001
        doc = _minimal(model_id)
        doc["_orqen"] = {"source": "none", "owasp_error": last, "hf_error": str(e)}
        return doc


def summarise(aibom: dict) -> dict:
    """Pulls the few fields the descriptor and passport header need."""
    comps = aibom.get("components") or [{}]
    c = comps[0]
    props = {p.get("name"): p.get("value") for p in c.get("properties", [])}
    return {
        "task": props.get("hf:pipeline_tag") or "text generation",
        "architecture": props.get("hf:architecture") or "transformer language model",
        "publisher": c.get("publisher") or c.get("group") or "unknown",
        "licenses": [l.get("license", {}).get("id")
                     for l in c.get("licenses", []) if isinstance(l, dict)],
        "source": aibom.get("_orqen", {}).get("source", "unknown"),
    }


def augment(aibom: dict, fingerprint: dict, scores: dict) -> dict:
    """Write measured behaviour back onto the CycloneDX component.

    This is the empirical-vs-declarative delta expressed inside the standard
    rather than beside it: the resulting document still validates as CycloneDX
    and can be dropped into any tool that consumes an AIBOM.
    """
    doc = json.loads(json.dumps(aibom))
    comps = doc.setdefault("components", [{"type": "machine-learning-model"}])
    c = comps[0]
    props = c.setdefault("properties", [])
    props.append({"name": NS + "fingerprint.version", "value": fingerprint.get("schema") and config.FINGERPRINT_VERSION})
    props.append({"name": NS + "fingerprint.digest", "value": fingerprint["digest"]})
    props.append({"name": NS + "suite.version", "value": config.PROBE_SUITE_VERSION})
    props.append({"name": NS + "assessment.overall", "value": scores["overall"]})
    for k, v in fingerprint["metrics"].items():
        props.append({"name": NS + k, "value": f"{v:.6f}"})
    doc.setdefault("_orqen", {})["augmented"] = True
    return doc
