"""orqen check <model_id> -- exit 1 on any red finding.

This is the Workflows-track surface: it is a real CI gate, not a wrapper that
prints the same thing the web app shows. Drop it in a GitHub Action and a model
bump that regresses fairness fails the build.
"""
from __future__ import annotations

import argparse
import json
import sys

from .pipeline import run
from .store import Store

BAR = {"green": "OK  ", "amber": "WARN", "red": "FAIL",
       "indeterminate": "----", "insufficient": "????"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="orqen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="audit a model and gate on the result")
    c.add_argument("model_id")
    c.add_argument("--json", action="store_true", help="emit the full passport")
    c.add_argument("--fail-on", choices=["red", "amber"], default="red")
    c.add_argument("--db", default=None)
    a = ap.parse_args(argv)

    p = run(a.model_id, store=Store(a.db))
    if a.json:
        print(json.dumps(p, indent=2))
        return _exit_code(p, a.fail_on)

    print(f"\norqen {p['suite_version']}  {p['model_id']}")
    print(f"fingerprint {p['fingerprint']['digest']}  "
          f"{p['fingerprint'].get('replicates', 1)} pass(es)  "
          f"{p['run']['calls']} calls  {p['run']['seconds']}s")
    basis = p.get("threshold_basis", "asserted")
    print(f"thresholds: {basis}"
          + (f" over {len(p.get('threshold_cohort') or [])} reference models"
             if basis != "asserted" else " (no reference cohort)") + "\n")
    for f in p["scores"]["findings"]:
        ci = (f"  +/-{1.96 * f['stderr']:.3f} (n={f['n']})"
              if f.get("n", 1) > 1 and f.get("stderr") else "")
        print(f"  [{BAR[f['grade']]}] {f['metric']:<38} {f['value']:.3f}{ci}"
              f"  (green <={f['green_at_or_below']}, amber <={f['amber_at_or_below']})")
    print(f"\n{p['scores']['verdict']}")
    if p["incidents"]:
        print("\nClosest documented incidents:")
        for m in p["incidents"]:
            print(f"  - {m['title']}  (sim {m['similarity']})")
            print(f"    {m['why']}")
    for w in p["warnings"]:
        print(f"\n  ! {w}")
    print(f"\npassport: /p/{p['slug']}\n")
    return _exit_code(p, a.fail_on)


def _exit_code(p, fail_on) -> int:
    """0 pass, 1 gate failure, 2 inconclusive. A CI job should treat 2 as a
    broken audit to investigate, not as a clean bill of health."""
    o = p["scores"]["overall"]
    if o in ("insufficient", "indeterminate"):
        # Both mean "no determination available", which a CI job must treat as a
        # result to investigate rather than a pass.
        return 2
    if fail_on == "red":
        return 1 if o == "red" else 0
    return 1 if o in ("red", "amber") else 0


if __name__ == "__main__":
    sys.exit(main())
