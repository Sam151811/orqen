from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class ProbeResult:
    name: str
    metrics: dict[str, float]              # metric_key -> value, higher = worse
    evidence: list[dict] = field(default_factory=list)
    calls: int = 0
    note: str = ""
    coverage: float = 1.0                  # fraction of items that returned cleanly
    errors: list[str] = field(default_factory=list)


class Probe:
    name: str = "probe"
    metric_keys: tuple[str, ...] = ()

    def run(self, chat, embed) -> ProbeResult:  # pragma: no cover
        raise NotImplementedError


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def split_ok(completions):
    """Partition a batch into (usable, error messages). A gateway hiccup on one
    prompt should cost that item, not the probe."""
    ok, errs = [], []
    for c in completions:
        if c.error or not (c.text or "").strip():
            errs.append(c.error or "empty response")
            ok.append(None)
        else:
            ok.append(c)
    return ok, errs
