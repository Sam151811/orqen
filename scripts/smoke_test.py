"""Pre-deploy smoke test. Run it before every push.

It exists because of a specific near-miss: doc_json was added to the Postgres
schema and not the SQLite one. Postgres was tested, SQLite was not, and local
development was broken for a whole working session while production was fine.
Anything that has two backends needs a test that runs both, or the two drift and
you find out from a stack trace at the worst moment.

  python scripts/smoke_test.py                      # sqlite only
  DATABASE_URL=postgresql://... python scripts/smoke_test.py   # both

Requires a gateway. Start scripts/fake_gateway.py first, or point the ORQEN_*
variables at a real one.
"""
from __future__ import annotations

import os
import sys
import traceback

sys.path.insert(0, ".")

PASS, FAIL = "  PASS", "  FAIL"
_results: list[tuple[bool, str, str]] = []


def check(name: str, fn):
    try:
        detail = fn()
        _results.append((True, name, detail or ""))
        print(f"{PASS}  {name} {detail or ''}")
    except Exception as exc:  # noqa: BLE001
        _results.append((False, name, str(exc)))
        print(f"{FAIL}  {name}\n{traceback.format_exc(limit=2)}")


def backend_suite(store, label: str):
    from orqen.pipeline import run
    from orqen.render import passport_html

    print(f"\n--- {label} ---")
    state = {}

    def audit():
        p = run("ref/biased-7b", store=store)
        state["p"] = p
        assert p["scores"]["findings"], "no findings produced"
        return f"grade={p['scores']['overall']} calls={p['run']['calls']}"

    def persisted():
        back = store.get_passport(state["p"]["slug"])
        assert back is not None, "passport did not persist"
        state["back"] = back
        return f"slug={back['slug']}"

    def fidelity():
        # The bug this file was written for: a served passport that is quietly
        # smaller than the one rendered in-process.
        live = passport_html(state["p"], "")
        served = passport_html(state["back"], "")
        assert live == served, (
            f"served passport differs from rendered "
            f"({len(served)} vs {len(live)} bytes) - a column is missing")
        return f"{len(live)} bytes, identical"

    def sections():
        h = passport_html(state["back"], "")
        for marker in ("§1", "§2", "§3", "§4", "§5", 'class="strip"'):
            assert marker in h, f"passport missing {marker}"
        return "all 5 clauses + assay strips"

    def cached():
        """A failed call is deliberately not cached, and the reference gateway
        429s a fraction of requests, so demanding exactly zero calls on re-audit
        is a flaky assertion rather than a strict one. The property that matters
        is that the cache eliminates nearly all of them."""
        first = state["p"]["run"]["calls"]
        p2 = run("ref/biased-7b", store=store)
        again = p2["run"]["calls"]
        assert again <= max(2, first * 0.1), (
            f"re-audit made {again} calls against {first} on the first pass; "
            f"the cache is not short-circuiting")
        assert p2["fingerprint"]["digest"] == state["p"]["fingerprint"]["digest"], \
            "fingerprint not reproducible across runs"
        return f"{again} calls vs {first}, digest stable"

    def cache_roundtrip():
        store.set("smoke:k", "v")
        assert store.get("smoke:k") == "v"
        store.set_vec("smoke:v", [0.5, 0.25])
        assert store.get_vec("smoke:v") == [0.5, 0.25]
        return "text + vector"

    def history():
        h = store.history("ref/biased-7b")
        assert len(h) >= 1, "history empty"
        return f"{len(h)} run(s)"

    check(f"[{label}] audit runs", audit)
    check(f"[{label}] passport persists", persisted)
    check(f"[{label}] served == rendered", fidelity)
    check(f"[{label}] all clauses render", sections)
    check(f"[{label}] cache short-circuits re-audit", cached)
    check(f"[{label}] cache round-trip", cache_roundtrip)
    check(f"[{label}] history query", history)


def main() -> int:
    from orqen import config
    from orqen.incidents import corpus
    from orqen.store import PostgresStore, SqliteStore

    print(f"provider={config.PROVIDER} embed={config.EMBED_PROVIDER} "
          f"dim={config.EMBED_DIM} suite={config.PROBE_SUITE_VERSION}")

    def corpus_loaded():
        st = corpus.stats()
        assert not st["error"], st["error"]
        assert st["n"] > 0, "incident corpus is empty - run incidents.ingest"
        return f"{st['n']} incidents at dim {st['dim']}"

    def thresholds_honest():
        # A cohort basis derived from fake models is worse than no basis: the
        # passport would claim measurement it does not have.
        if config.THRESHOLD_BASIS == "asserted":
            return "asserted (no cohort claimed)"
        assert config.COHORT, "cohort basis declared with no cohort listed"
        fake = [m for m in config.COHORT if m.startswith("ref/")]
        assert not fake, (
            f"thresholds derived from fake gateway personas {fake} - delete "
            f"data/thresholds.json before deploying")
        return f"cohort of {len(config.COHORT)}"

    check("incident corpus loads", corpus_loaded)
    check("threshold basis is honest", thresholds_honest)

    tmp = "/tmp/orqen-smoke.db"
    if os.path.exists(tmp):
        os.remove(tmp)
    backend_suite(SqliteStore(tmp), "sqlite")

    dsn = os.getenv("DATABASE_URL", "")
    if dsn.startswith("postgres"):
        backend_suite(PostgresStore(dsn), "postgres")
    else:
        print("\n--- postgres: SKIPPED (set DATABASE_URL to include it) ---")

    failed = [r for r in _results if not r[0]]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} passed")
    for _, name, detail in failed:
        print(f"  FAILED: {name} - {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
