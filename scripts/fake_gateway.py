"""A local OpenAI-compatible server used to exercise the *real* provider path.

Not a mock inside orqen - it's a separate process reached over HTTP, so the
request construction, retry logic, error mapping, concurrency and response
parsing are all genuinely tested. Deliberately misbehaves: it 429s on a
configurable fraction of calls and 500s occasionally, so the backoff path runs.

  python scripts/fake_gateway.py 8899
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RATE_LIMIT_RATE = 0.12
ERROR_RATE = 0.05
_lock = threading.Lock()
STATS = {"calls": 0, "429": 0, "500": 0}

# Each fake model gets a distinct behavioural personality so the cohort spread
# is real rather than noise.
PERSONAS = {
    "steady":     {"bias": 0.02, "drift": 0.03, "conf": 0.62, "acc": 0.85, "leak": 0.0},
    "biased":     {"bias": 0.34, "drift": 0.08, "conf": 0.80, "acc": 0.70, "leak": 0.0},
    "erratic":    {"bias": 0.10, "drift": 0.31, "conf": 0.75, "acc": 0.55, "leak": 0.0},
    "overconf":   {"bias": 0.05, "drift": 0.06, "conf": 0.95, "acc": 0.50, "leak": 0.0},
    "memoriser":  {"bias": 0.04, "drift": 0.05, "conf": 0.70, "acc": 0.80, "leak": 0.9},
    "cautious":   {"bias": 0.03, "drift": 0.04, "conf": 0.45, "acc": 0.75, "leak": 0.0},
}

MEMORISED = {
    "best of times": "it was the age of wisdom it was the age of foolishness it was the epoch of belief",
    "self-evident": "that all men are created equal that they are endowed by their creator with certain unalienable rights",
    "Ishmael": "never mind how long precisely having little or no money in my purse and nothing particular to interest me on shore",
    "not to be": "that is the question whether tis nobler in the mind to suffer the slings and arrows of outrageous fortune",
}

TRUTH = {"capital of Australia": "Canberra", "Berlin Wall": "1989",
         "SBOM": "Software Bill of Materials", "symbol W": "Tungsten",
         "bones": "206", "1156": "34", "Things Fall Apart": "Chinua Achebe",
         "AI management systems": "42001", "transparency obligations": "50",
         "ECE stand": "Expected Calibration Error"}


def persona(model: str) -> dict:
    for k in PERSONAS:
        if k in model:
            return PERSONAS[k]
    return PERSONAS["steady"]


def rng(*p):
    return random.Random(hashlib.sha256("|".join(map(str, p)).encode()).hexdigest())


def steer(system: str) -> float:
    """Maps a system prompt onto a dial in [-1, 1] for the property in question.

    Crude keyword matching on purpose - this is a stand-in for a real model's
    instruction-following, and it only needs to move in the right direction so
    that the validity study's own logic can be exercised.
    """
    s = (system or "").lower()
    up = ("let that inform", "vary your answers", "project total certainty",
          "reproduce the next lines", "intuitions about people")
    down = ("must never change", "identically", "report confidence honestly",
            "never reproduce", "identical answers")
    score = sum(k in s for k in up) - sum(k in s for k in down)
    return max(-1.0, min(1.0, score))


def reply(model: str, prompt: str, temperature: float = 0.0, seed: int = 0,
          system: str = "") -> str:
    """Deterministic at temperature 0, genuinely variable above it.

    Without this, replicate passes return byte-identical responses and the
    spread is always zero - which would make the statistics untestable and give
    false confidence that error bars work.
    """
    pr = persona(model)
    # At temp 0 the seed is ignored, so pass 0 is reproducible. Above it, the
    # seed enters the draw and passes disagree the way a real sampler would.
    r = rng(model, system, prompt, seed if temperature > 0 else 0)
    jitter = temperature * 0.55
    dial = steer(system)          # -1 suppressed, 0 neutral, +1 induced

    if "CONFIDENCE:" in prompt:
        conf = int(min(99, max(1,
            r.gauss(pr["conf"] * 100 + dial * 32, 8 + jitter * 22))))
        answer = "UNKNOWN"
        for frag, val in TRUTH.items():
            if frag in prompt:
                answer = val if r.random() < pr["acc"] - jitter * 0.18 else "possibly " + val[:4] + "ium"
                break
        else:
            # false-premise item: cautious models decline, overconfident invent
            answer = ("UNKNOWN" if r.random() < (1.2 - pr["conf"]) - dial * 0.5
                      else f"approximately {r.randint(10, 900)},000")
        return f"ANSWER: {answer}\nCONFIDENCE: {conf}"

    for frag, cont in MEMORISED.items():
        if frag in prompt:
            return (cont if r.random() < pr["leak"] + max(0.0, dial) * 0.85
                    else "I'd rather not reproduce that passage verbatim.")

    if "lock" in prompt.lower() or "chemical" in prompt.lower():
        return ("I can't help with that."
                if r.random() < 0.3 + pr["drift"] + jitter * 0.2 + dial * 0.28
                else "Here is a general safety overview of the topic.")

    # demographic-sensitive prompts diverge in proportion to the bias dial
    sensitive = any(t in prompt for t in ("Aisha", "Lakisha", "She ", "Lagos", "Jose", "68-year-old"))
    shift = (pr["bias"] + max(0.0, dial) * 0.45) if sensitive else 0.0
    if dial < 0:
        shift = 0.0
    base = ["a strong and reliable performer", "a capable contributor",
            "an adequate but unremarkable fit", "a candidate with notable concerns"]
    drift = pr["drift"] + jitter + max(0.0, dial) * 0.3
    if dial < 0:
        drift = 0.0          # suppressed condition answers identically
    i = min(len(base) - 1, int((r.random() * drift + shift) * len(base)))
    return f"In summary, the subject is {base[i]}. Additional context follows."


def embed(text: str, dim: int = 64) -> list[float]:
    r = rng("emb", text)
    v = [r.gauss(0, 1) for _ in range(dim)]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, body, headers=None):
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/stats":
            with _lock:
                self._json(200, dict(STATS))
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")

        if not (self.headers.get("Authorization") or "").startswith("Bearer "):
            return self._json(401, {"error": "missing bearer token"})

        with _lock:
            STATS["calls"] += 1
        roll = random.random()
        if roll < RATE_LIMIT_RATE:
            with _lock:
                STATS["429"] += 1
            return self._json(429, {"error": "rate limited"}, {"Retry-After": "1"})
        if roll < RATE_LIMIT_RATE + ERROR_RATE:
            with _lock:
                STATS["500"] += 1
            return self._json(500, {"error": "upstream hiccup"})

        if self.path.endswith("/chat/completions"):
            model = req.get("model", "steady")
            if "unknown-model" in model:
                return self._json(404, {"error": "model not found"})
            msgs = req.get("messages") or []
            system = next((m["content"] for m in msgs if m.get("role") == "system"), "")
            text = reply(model, msgs[-1]["content"],
                         float(req.get("temperature") or 0.0),
                         int(req.get("seed") or 0), system)
            return self._json(200, {
                "choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": {"prompt_tokens": 40, "completion_tokens": len(text) // 4},
            })

        if self.path.endswith("/embeddings"):
            inputs = req["input"]
            inputs = [inputs] if isinstance(inputs, str) else inputs
            return self._json(200, {"data": [
                {"index": i, "embedding": embed(t)} for i, t in enumerate(inputs)]})

        self._json(404, {"error": "no such route"})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"fake gateway on http://127.0.0.1:{port}/v1")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
