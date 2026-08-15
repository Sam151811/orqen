"""Inference + embedding adapters.

One protocol (OpenAI chat/completions + embeddings) covers HF Inference
Providers, Groq, Cerebras, Together, OpenRouter and OpenAI itself.

Three things here exist only because of real gateways:
  - retry with backoff that honours Retry-After, because free tiers 429 hard;
  - a thread pool, because 48 serial calls at 1.5s each blows the demo budget;
  - an alias map, because the audited model's *identity* is its HF id but the
    string a given gateway wants is often different (groq calls it
    llama-3.1-8b-instant). Identity and routing are deliberately separate.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import config


class ProviderError(RuntimeError):
    pass


class AuthError(ProviderError):
    pass


class ModelUnavailable(ProviderError):
    pass


class RateLimited(ProviderError):
    def __init__(self, msg, retry_after: float | None = None):
        super().__init__(msg)
        self.retry_after = retry_after


class BudgetExceeded(RuntimeError):
    pass


class DeadlineExceeded(BudgetExceeded):
    pass


@dataclass
class CallBudget:
    """Thread-safe: probes fan out, so the counter has to be locked.

    Guards two resources - number of calls and wall-clock time. The second
    matters more in production: call count protects credits, the deadline
    protects the request from hanging when the gateway is unreachable.
    """
    limit: int = config.MAX_CALLS_PER_RUN
    deadline_s: float = config.RUN_DEADLINE_S
    started: float = field(default_factory=time.monotonic)
    used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.started > self.deadline_s

    @property
    def remaining_s(self) -> float:
        return max(0.0, self.deadline_s - (time.monotonic() - self.started))

    def spend(self, n: int = 1) -> None:
        if self.expired:
            raise DeadlineExceeded(
                f"run exceeded its {self.deadline_s:g}s wall-clock deadline")
        with self._lock:
            if self.used + n > self.limit:
                raise BudgetExceeded(
                    f"run would exceed {self.limit} model calls "
                    f"(raise ORQEN_MAX_CALLS if this is intentional)")
            self.used += n

    def record_usage(self, usage: dict) -> None:
        with self._lock:
            self.prompt_tokens += usage.get("prompt_tokens", 0) or 0
            self.completion_tokens += usage.get("completion_tokens", 0) or 0

    def snapshot(self) -> dict:
        with self._lock:
            return {"calls": self.used, "prompt_tokens": self.prompt_tokens,
                    "completion_tokens": self.completion_tokens}


@dataclass
class Completion:
    text: str
    cached: bool = False
    error: str | None = None


# --- model identity vs gateway routing --------------------------------------
# ORQEN_MODEL_ALIASES='{"meta-llama/Llama-3.1-8B-Instruct":"llama-3.1-8b-instant"}'
def _load_aliases() -> dict[str, str]:
    raw = os.getenv("ORQEN_MODEL_ALIASES", "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


ALIASES = _load_aliases()


def route(model_id: str) -> str:
    return ALIASES.get(model_id, model_id)


# --- transport ---------------------------------------------------------------
def _post(url: str, key: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}",
                 "User-Agent": "orqen/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read()[:400].decode(errors="replace")
        if e.code in (401, 403):
            raise AuthError(f"{e.code}: check ORQEN_API_KEY. {body}") from e
        if e.code == 429:
            ra = e.headers.get("Retry-After")
            raise RateLimited(f"429: {body}",
                              float(ra) if ra and ra.isdigit() else None) from e
        if e.code in (404, 400):
            raise ModelUnavailable(f"{e.code}: {body}") from e
        raise ProviderError(f"{e.code}: {body}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ProviderError(f"transport: {e}") from e


def _with_retry(fn, attempts: int = 4, budget=None):
    delay = 1.0
    last = None
    for i in range(attempts):
        if budget is not None and budget.expired:
            raise last or ProviderError("deadline reached before first attempt")
        try:
            return fn()
        except RateLimited as e:
            last = e
            wait = e.retry_after if e.retry_after else delay
        except ProviderError as e:
            last = e
            if isinstance(e, (AuthError, ModelUnavailable)):
                raise            # retrying these is pointless
            wait = delay
        if i == attempts - 1:
            break
        if budget is not None:
            # Never sleep past the deadline; a retry that lands after it is
            # wasted latency the caller is paying for.
            wait = min(wait, budget.remaining_s)
            if wait <= 0:
                break
        time.sleep(wait + random.uniform(0, 0.3))   # jitter
        delay *= 2
    raise last  # type: ignore[misc]


class ChatProvider:
    """Executes the audited model."""

    def __init__(self, model_id: str, budget: CallBudget, cache=None,
                 temperature: float = 0.0, seed: int = 0, system: str = ""):
        self.model_id = model_id
        self.routed = route(model_id)
        self.budget = budget
        self.cache = cache
        # Repeated measurement needs genuine sampling variation, so replicate
        # runs are issued at a non-zero temperature with a distinct seed. The
        # cache key includes both, so replicates do not collapse onto each other.
        self.temperature = temperature
        self.seed = seed
        # Only used by the validity study, which needs to induce a known amount
        # of the property a probe claims to detect. Normal audits leave it empty:
        # injecting a system prompt would measure the prompt, not the model.
        self.system = system

    def _key(self, prompt: str, temperature: float, seed: int) -> str:
        return hashlib.sha256(
            f"{self.model_id}|{self.system}|{prompt}|{temperature}|{seed}"
            f"|{config.PROBE_SUITE_VERSION}".encode()
        ).hexdigest()

    def complete(self, prompt: str, temperature: float | None = None,
                 seed: int | None = None) -> Completion:
        return self.complete_many([prompt], temperature, seed)[0]

    def complete_many(self, prompts: list[str], temperature: float | None = None,
                      seed: int | None = None) -> list[Completion]:
        """Cache-then-fan-out. Order is preserved; failures come back as
        Completion(error=...) rather than raising, so one dead call degrades a
        single metric instead of the whole passport."""
        temperature = self.temperature if temperature is None else temperature
        seed = self.seed if seed is None else seed
        out: list[Completion | None] = [None] * len(prompts)
        todo: list[tuple[int, str, str]] = []

        for i, p in enumerate(prompts):
            ck = self._key(p, temperature, seed)
            hit = self.cache.get(ck) if self.cache else None
            if hit is not None:
                out[i] = Completion(hit, cached=True)
            else:
                todo.append((i, p, ck))

        if todo:
            self.budget.spend(len(todo))
            workers = min(config.MAX_CONCURRENCY, len(todo))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for (i, _, ck), comp in zip(
                        todo, pool.map(lambda t: self._one(t[1], temperature, seed), todo)):
                    out[i] = comp
                    if comp.error is None and self.cache:
                        self.cache.set(ck, comp.text)
        return [o for o in out]  # type: ignore[return-value]

    def _one(self, prompt: str, temperature: float, seed: int) -> Completion:
        if config.PROVIDER == "mock":
            return Completion(_mock_completion(self.model_id, prompt, temperature,
                                               seed, self.system))
        if self.budget.expired:
            return Completion("", error="DeadlineExceeded: run deadline reached")
        try:
            timeout = min(config.CALL_TIMEOUT_S, max(2.0, self.budget.remaining_s))
            data = _with_retry(lambda: _post(
                f"{config.BASE_URL.rstrip('/')}/chat/completions",
                config.API_KEY,
                {"model": self.routed,
                 "messages": ([{"role": "system", "content": self.system}]
                              if self.system else [])
                             + [{"role": "user", "content": prompt}],
                 "temperature": temperature,
                 "max_tokens": config.MAX_TOKENS,
                 "seed": seed},
                timeout), budget=self.budget)
        except ProviderError as e:
            return Completion("", error=f"{type(e).__name__}: {e}")

        self.budget.record_usage(data.get("usage") or {})
        try:
            return Completion(data["choices"][0]["message"]["content"] or "")
        except (KeyError, IndexError, TypeError):
            return Completion("", error=f"unexpected response shape: {str(data)[:200]}")


class EmbeddingProvider:
    def __init__(self, cache=None):
        self.cache = cache

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float] | None] = [None] * len(texts)
        missing, idx = [], []
        for i, t in enumerate(texts):
            ck = hashlib.sha256(f"emb|{config.EMBED_MODEL}|{t}".encode()).hexdigest()
            hit = self.cache.get_vec(ck) if self.cache else None
            if hit is not None:
                out[i] = hit
            else:
                missing.append(t)
                idx.append((i, ck))

        for start in range(0, len(missing), 64):
            chunk = missing[start:start + 64]
            if config.EMBED_PROVIDER == "mock":
                vecs = [_mock_embed(t) for t in chunk]
            else:
                payload = {"model": config.EMBED_MODEL, "input": chunk}
                # OpenAI v3 embeddings accept a dimensions parameter; asking for
                # 256 instead of 1536 cuts corpus scan time by 6x. Providers
                # that reject it fall through to truncation below.
                if config.EMBED_REQUEST_DIM:
                    payload["dimensions"] = config.EMBED_DIM
                try:
                    data = _with_retry(lambda: _post(
                        f"{config.EMBED_BASE_URL.rstrip('/')}/embeddings",
                        config.EMBED_API_KEY, payload, config.CALL_TIMEOUT_S))
                except ProviderError:
                    payload.pop("dimensions", None)
                    data = _with_retry(lambda: _post(
                        f"{config.EMBED_BASE_URL.rstrip('/')}/embeddings",
                        config.EMBED_API_KEY, payload, config.CALL_TIMEOUT_S))
                vecs = [d["embedding"][:config.EMBED_DIM] for d in
                        sorted(data["data"], key=lambda d: d.get("index", 0))]
            for (i, ck), v in zip(idx[start:start + 64], vecs):
                out[i] = v
                if self.cache:
                    self.cache.set_vec(ck, v)
        return out  # type: ignore[return-value]


def clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def cosine(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a)) or 1e-9
    db = math.sqrt(sum(y * y for y in b)) or 1e-9
    return num / (da * db)


# --- mock backends -----------------------------------------------------------
def _rng(*parts) -> random.Random:
    return random.Random(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest())


def _mock_completion(model_id: str, prompt: str, temperature: float, seed: int,
                     system: str = "") -> str:
    r = _rng(model_id, system, prompt, seed if temperature > 0 else 0)
    bias = _rng(model_id).random()
    if "CONFIDENCE:" in prompt:
        return f"ANSWER: {r.choice(['Canberra', '1989', 'UNKNOWN', 'Tungsten'])}\nCONFIDENCE: {r.randint(40, 99)}"
    fillers = ["Certainly.", "In short,", "Broadly speaking,", "It depends, but"]
    tail = ["a reasonable candidate", "generally considered suitable",
            "not typically recommended", "an excellent fit"]
    pick = int(bias * len(tail)) if ("Aisha" in prompt or "She" in prompt) else 0
    return f"{r.choice(fillers)} the subject is {tail[pick % len(tail)]}. {r.random():.4f}"


def _mock_embed(text: str) -> list[float]:
    r = _rng("emb", text)
    v = [r.gauss(0, 1) for _ in range(config.EMBED_DIM)]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]
