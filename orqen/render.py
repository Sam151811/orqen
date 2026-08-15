"""Passport rendering.

The output is a certificate of analysis, not a dashboard. A lab issuing a
materials test report states what was measured, against what specification,
by what method, with what coverage, and signs it. That is exactly the shape of
what Orqen produces, and it sets the reader's expectations correctly: this is a
document of record, not a live monitor.

Server-rendered, single file, no client framework. The passport works with
JavaScript disabled, in an incognito window, and prints to PDF cleanly -
properties that matter more for a compliance artefact than any interaction
would.
"""
from __future__ import annotations

import datetime as _dt
import html
import json

CONFORMANCE = {
    "green": ("PASS", "Within specification"),
    "amber": ("REVIEW", "Within review band"),
    "red": ("FAIL", "Outside specification"),
    "indeterminate": ("NO CALL", "Interval spans the limit"),
    "insufficient": ("INCONCLUSIVE", "Insufficient measurement coverage"),
}

METRIC_LABELS = {
    "fairness.excess_divergence": "Demographic divergence, net of control",
    "fairness.control_divergence": "Within-group control (noise floor)",
    "fairness.max_pair_divergence": "Counterfactual pair divergence, raw",
    "fairness.sentiment_gap": "Tone gap across demographic variants",
    "robustness.paraphrase_variance": "Output variance under paraphrase",
    "robustness.refusal_instability": "Refusal instability",
    "calibration.ece": "Expected calibration error",
    "calibration.overconfidence": "Mean overconfidence",
    "calibration.accuracy": "Error rate on labelled set",
    "calibration.false_premise_rate": "False-premise fabrication rate",
    "leakage.verbatim_rate": "Verbatim canary reproduction rate",
    "leakage.max_run": "Longest memorised token run, normalised",
}

# The certificate now shares the application's palette and type system. What
# separates it is structure, not brightness: no scene, no motion, numbered
# clauses, a tighter measure, a document-control footer - and it inverts to white
# paper on print, which is the one place a document genuinely needs to behave
# differently from an interface.
DOC_CSS = """
body{font-family:var(--font-prose);font-weight:300;line-height:1.6}
.sheet{position:relative;z-index:2;max-width:64rem;margin:0 auto;
  border-left:1px solid var(--rule);border-right:1px solid var(--rule)}
.doc{max-width:64rem;margin:0 auto;padding:0 calc(var(--sp)*6) calc(var(--sp)*20)}

/* masthead ---------------------------------------------------------------- */
.mast{border-bottom:1px solid var(--rule-strong);padding:calc(var(--sp)*12) calc(var(--sp)*8)}
.mast-top{display:flex;justify-content:space-between;align-items:baseline;
  gap:calc(var(--sp)*4);flex-wrap:wrap}
.brand{font-family:var(--font-body);font-weight:500;font-size:var(--text-xs);
  letter-spacing:.22em;text-transform:uppercase}
.doctype{font-family:var(--font-body);font-size:var(--text-xs);letter-spacing:.18em;
  text-transform:uppercase;color:var(--dim)}
.specimen{font-family:var(--font-display);font-size:clamp(1.5rem,4vw,var(--text-3xl));
  font-weight:200;letter-spacing:-.03em;margin:calc(var(--sp)*6) 0 0;
  word-break:break-word;line-height:1.15}
.specimen-sub{font-size:var(--text-sm);color:var(--dim);margin:calc(var(--sp)*3) 0 0}

/* key/value grid ---------------------------------------------------------- */
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:0;
  border-bottom:1px solid var(--rule);margin:0}
.kv > div{padding:calc(var(--sp)*4) calc(var(--sp)*8);
  border-right:1px solid rgba(255,255,255,.07)}
.kv dt{font-family:var(--font-body);font-size:var(--text-xs);letter-spacing:.16em;
  text-transform:uppercase;color:var(--dim);margin:0 0 calc(var(--sp)*2)}
.kv dd{margin:0;font-family:var(--font-body);font-size:var(--text-sm);
  word-break:break-word;color:var(--white)}

/* determination ----------------------------------------------------------- */
.determination{display:flex;gap:calc(var(--sp)*8);align-items:flex-start;
  padding:calc(var(--sp)*10) calc(var(--sp)*8);border-bottom:1px solid var(--rule)}
.stamp{flex:0 0 auto;border:1px solid currentColor;padding:calc(var(--sp)*3) calc(var(--sp)*5);
  font-family:var(--font-body);font-size:var(--text-lg);font-weight:400;
  letter-spacing:.1em;text-transform:uppercase;line-height:1.1;white-space:nowrap}
.stamp small{display:block;font-size:var(--text-xs);letter-spacing:.14em;
  font-weight:400;color:var(--dim);margin-top:calc(var(--sp)*2);text-transform:none;
  letter-spacing:.06em}
/* Monochrome, so severity is carried by weight and tone, never by hue alone -
   and the stamp always spells the determination out in words. */
.g-red .stamp{color:var(--white);border-width:2px}
.g-amber .stamp{color:var(--white)}
.g-indeterminate .stamp{color:var(--mid)}
.g-green .stamp{color:var(--mid)}
.g-insufficient .stamp{color:var(--dim);font-style:italic}
.determination p{margin:0;font-size:var(--text-base);color:var(--white)}
.tally{margin:calc(var(--sp)*4) 0 0 !important;font-family:var(--font-body);
  font-size:var(--text-xs);letter-spacing:.08em;color:var(--dim) !important}

/* clauses ----------------------------------------------------------------- */
.sec{padding:calc(var(--sp)*12) calc(var(--sp)*8);border-bottom:1px solid var(--rule)}
.sec:last-child{border-bottom:0}
.sec > h2{font-family:var(--font-body);font-size:var(--text-xs);letter-spacing:.18em;
  text-transform:uppercase;color:var(--white);margin:0 0 calc(var(--sp)*8);
  display:flex;align-items:baseline;gap:calc(var(--sp)*3)}
.sec > h2 .clause{color:var(--dim);letter-spacing:0}
.sec > h2::after{content:"";flex:1;height:1px;background:var(--rule)}
.sec .lede{color:var(--mid);font-size:var(--text-sm);max-width:60ch;
  margin:0 0 calc(var(--sp)*8)}
.sec .lede strong{color:var(--white);font-weight:400}
.sec .lede a{color:var(--white)}
.sec .kv{border-bottom:0;border-top:1px solid rgba(255,255,255,.07)}
.sec .kv > div{padding-left:0}

/* assay strips ------------------------------------------------------------ */
.assay{border-top:1px solid rgba(255,255,255,.07)}
.row{padding:calc(var(--sp)*5) 0;border-bottom:1px solid rgba(255,255,255,.07)}
.row-head{display:flex;justify-content:space-between;align-items:baseline;
  gap:calc(var(--sp)*4);margin-bottom:calc(var(--sp)*3);flex-wrap:wrap}
.row-name{font-size:var(--text-sm);color:var(--white)}
.row-key{display:block;font-family:var(--font-body);font-size:var(--text-xs);
  color:var(--dim);margin-top:calc(var(--sp)*1)}
.row-val{font-family:var(--font-body);font-size:var(--text-xl);font-weight:200;
  font-variant-numeric:tabular-nums;white-space:nowrap;letter-spacing:-.02em}
.row-val b{font-weight:400}
.verdict-tag{font-family:var(--font-body);font-size:var(--text-xs);font-weight:400;
  letter-spacing:.12em;padding:calc(var(--sp)*1) calc(var(--sp)*2);
  border:1px solid currentColor;margin-left:calc(var(--sp)*3);text-transform:uppercase}
.g-red .verdict-tag{color:var(--white)}
.g-amber .verdict-tag,.g-indeterminate .verdict-tag{color:var(--mid)}
.g-green .verdict-tag{color:var(--dim)}
.strip{width:100%;height:34px;display:block;overflow:visible}
.strip .band-pass{fill:#fff;opacity:.035}
.strip .band-review{fill:#fff;opacity:.075}
.strip .band-fail{fill:#fff;opacity:.13}
.strip .axis{stroke:var(--rule);stroke-width:1}
.strip .lim{stroke:var(--dim);stroke-width:1;stroke-dasharray:2 2}
.strip .peer{stroke:var(--dim);stroke-width:1}
.strip .ci{stroke:var(--mid);stroke-width:5;opacity:.30;stroke-linecap:butt}
.strip .measured{stroke:var(--white);stroke-width:2.5}
.strip text{font-family:var(--font-body);font-size:8.5px;fill:var(--dim)}
.strip-legend{font-family:var(--font-body);font-size:var(--text-xs);color:var(--dim);
  margin:calc(var(--sp)*2) 0 0;line-height:1.5}

/* exhibits ---------------------------------------------------------------- */
.evidence{border:1px solid var(--rule);border-radius:var(--radius);
  margin:0 0 calc(var(--sp)*3);background:var(--panel)}
.evidence > summary{cursor:pointer;padding:calc(var(--sp)*4) calc(var(--sp)*5);
  font-family:var(--font-body);font-size:var(--text-xs);letter-spacing:.14em;
  text-transform:uppercase;color:var(--mid)}
.evidence > summary:hover{color:var(--white)}
.evidence > summary:focus-visible{outline:2px solid var(--white);outline-offset:-2px}
.evidence[open] > summary{border-bottom:1px solid var(--rule);color:var(--white)}
.evidence .body{padding:calc(var(--sp)*5)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:calc(var(--sp)*5);
  margin:0 0 calc(var(--sp)*5)}
.pair > div{border-left:1px solid var(--rule-strong);padding-left:calc(var(--sp)*4)}
.pair h4{font-family:var(--font-body);font-size:var(--text-xs);color:var(--dim);
  margin:0 0 calc(var(--sp)*2);font-weight:400;letter-spacing:.06em}
.pair p{margin:0;font-size:var(--text-sm);color:var(--mid)}
.method{font-size:var(--text-sm);color:var(--dim);margin:0 0 calc(var(--sp)*5)}
table.bins{border-collapse:collapse;width:100%;font-family:var(--font-body);
  font-size:var(--text-xs);margin:0 0 calc(var(--sp)*5)}
table.bins th,table.bins td{border:1px solid var(--rule);padding:calc(var(--sp)*2);
  text-align:right;font-variant-numeric:tabular-nums;color:var(--mid);
  white-space:nowrap;cursor:default}
table.bins th{color:var(--dim);font-weight:400;text-transform:none;letter-spacing:0}
table.bins th:hover{color:var(--dim)}
table.bins td:first-child,table.bins th:first-child{text-align:left}

/* incidents --------------------------------------------------------------- */
.descriptor{border-left:2px solid var(--white);padding-left:calc(var(--sp)*5);
  margin:0 0 calc(var(--sp)*8);font-size:var(--text-base);color:var(--white)}
.incident{border-top:1px solid rgba(255,255,255,.07);padding:calc(var(--sp)*5) 0}
.incident h3{margin:0 0 calc(var(--sp)*2);font-size:var(--text-base);font-weight:400;
  color:var(--white)}
.incident h3 a{text-decoration-color:var(--rule-strong);text-underline-offset:3px}
.incident p{margin:calc(var(--sp)*2) 0;font-size:var(--text-sm);color:var(--dim)}
.incident .why{color:var(--mid)}
.meta-line{font-family:var(--font-body);font-size:var(--text-xs);color:var(--dim);
  margin:calc(var(--sp)*2) 0 0 !important}
.conf-strong{color:var(--white)}.conf-moderate{color:var(--mid)}.conf-weak{color:var(--dim)}

/* coverage matrix --------------------------------------------------------- */
.cov{border-collapse:collapse;width:100%;font-size:var(--text-sm);
  margin:0 0 calc(var(--sp)*6)}
.cov th{text-align:left;font-family:var(--font-body);font-size:var(--text-xs);
  letter-spacing:.14em;text-transform:uppercase;color:var(--dim);
  padding:0 calc(var(--sp)*4) calc(var(--sp)*3) 0;border-bottom:1px solid var(--rule);
  cursor:default}
.cov th:hover{color:var(--dim)}
.cov td{padding:calc(var(--sp)*4) calc(var(--sp)*4) calc(var(--sp)*4) 0;
  border-bottom:1px solid rgba(255,255,255,.07);vertical-align:top;color:var(--mid);
  white-space:normal}
.cov td.ref{font-family:var(--font-body);font-size:var(--text-xs);white-space:nowrap;
  color:var(--dim)}
.cov td.req{color:var(--white);font-weight:400}
.cov td.det{color:var(--dim);font-size:var(--text-sm)}
.lvl{font-family:var(--font-body);font-size:var(--text-xs);letter-spacing:.1em;
  text-transform:uppercase;padding:calc(var(--sp)*1) calc(var(--sp)*2);
  border:1px solid currentColor;white-space:nowrap;display:inline-block}
.lvl-measured{color:var(--white)}
.lvl-partial{color:var(--mid)}
.lvl-declared{color:var(--mid)}
.lvl-external{color:var(--dim)}

/* comparison -------------------------------------------------------------- */
.cmp{border-collapse:collapse;width:100%;font-family:var(--font-body);
  font-size:var(--text-sm)}
.cmp th{text-align:right;font-size:var(--text-xs);letter-spacing:.14em;
  text-transform:uppercase;color:var(--dim);padding:0 calc(var(--sp)*4) calc(var(--sp)*3);
  border-bottom:1px solid var(--rule);cursor:default}
.cmp th:first-child{text-align:left}
.cmp th:hover{color:var(--dim)}
.cmp td{padding:calc(var(--sp)*3) calc(var(--sp)*4);
  border-bottom:1px solid rgba(255,255,255,.07);text-align:right;
  font-variant-numeric:tabular-nums;color:var(--mid)}
.cmp td:first-child{text-align:left}
.cmp .up{color:var(--white);font-weight:500}
.cmp .down{color:var(--dim)}
.cmp .flat{color:var(--dim)}

/* attestation + notices --------------------------------------------------- */
.attest{display:flex;gap:calc(var(--sp)*5);align-items:flex-start;
  padding:calc(var(--sp)*6) calc(var(--sp)*8);border-top:1px solid var(--rule);
  font-family:var(--font-body);font-size:var(--text-xs);color:var(--dim);
  flex-wrap:wrap;line-height:1.6}
.attest .seal{border:1px solid var(--white);color:var(--white);
  padding:calc(var(--sp)*2) calc(var(--sp)*3);font-size:var(--text-xs);
  letter-spacing:.14em;text-transform:uppercase;white-space:nowrap}
.attest .seal.warn{border-color:var(--dim);color:var(--dim)}
.attest code{word-break:break-all;color:var(--mid)}
.notice{border:1px solid var(--rule-strong);border-left-width:2px;
  padding:calc(var(--sp)*4) calc(var(--sp)*5);margin:0 0 calc(var(--sp)*5);
  font-size:var(--text-sm);color:var(--mid);background:var(--panel)}
.notice b{display:block;font-family:var(--font-body);font-size:var(--text-xs);
  letter-spacing:.14em;text-transform:uppercase;color:var(--white);
  margin-bottom:calc(var(--sp)*2)}

/* document control -------------------------------------------------------- */
.control{padding:calc(var(--sp)*6) calc(var(--sp)*8) calc(var(--sp)*10);
  border-top:1px solid var(--rule-strong);font-family:var(--font-body);
  font-size:var(--text-xs);letter-spacing:.1em;text-transform:uppercase;
  color:var(--dim);display:flex;justify-content:space-between;
  gap:calc(var(--sp)*5);flex-wrap:wrap}
.control a{color:var(--mid);text-decoration:none}
.control a:hover{color:var(--white)}

@media (max-width:680px){
  .determination{flex-direction:column;gap:calc(var(--sp)*5)}
  .pair{grid-template-columns:1fr}
  .mast,.determination,.sec,.control,.attest,.kv > div{
    padding-left:calc(var(--sp)*4);padding-right:calc(var(--sp)*4)}
  .sheet{border-left:0;border-right:0}
}

/* PRINT
   The one place a document must behave differently from an interface. A
   compliance artefact gets attached to a review pack, and a full-bleed black
   page is both unreadable on paper and an ink cartridge. Everything inverts. */
@media print{
  body{background:#fff !important;color:#000 !important}
  #scene,#scene-veil,.bar,.cue{display:none !important}
  .sheet{border:0;max-width:none}
  .specimen,.row-val,.tile-value{color:#000 !important}
  .kv dd,.row-name,.determination p,.descriptor,.incident h3,
  .cov td.req,.sec .lede strong{color:#000 !important}
  .lede,.method,.pair p,.incident p,.incident .why,.cov td,.cov td.det,
  .strip-legend,.meta-line,.tally,.attest,.control{color:#333 !important}
  .kv dt,.sec > h2,.doctype,.brand{color:#000 !important}
  .kv,.kv > div,.sec,.mast,.determination,.row,.incident,.control,.attest,
  .evidence,.cov td,.cov th,.cmp td,.cmp th,table.bins th,table.bins td,
  .pair > div,.notice{border-color:#bbb !important}
  .mast,.control{border-color:#000 !important}
  .stamp{color:#000 !important;border-color:#000 !important}
  .verdict-tag,.lvl,.attest .seal{color:#000 !important;border-color:#000 !important}
  .strip .band-pass{fill:#000;opacity:.05}
  .strip .band-review{fill:#000;opacity:.11}
  .strip .band-fail{fill:#000;opacity:.2}
  .strip .measured{stroke:#000}
  .strip .axis,.strip .lim,.strip .peer{stroke:#666}
  .strip .ci{stroke:#666;opacity:.35}
  .strip text{fill:#444}
  .evidence,.notice{background:transparent !important}
  .evidence[open] > summary{display:none}
  details{break-inside:avoid}
  .row,.incident{break-inside:avoid}
  a{color:#000 !important}
}
"""


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _shell(title: str, body: str, desc: str = "") -> str:
    """No canvas and no application script: a document does not animate, and the
    certificate has to render identically in an email client, an incognito window
    and a print preview."""
    from .ui import CSS as APP_CSS, FONTS, _bar

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#000000">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="article">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
{FONTS}
<style>{APP_CSS}{DOC_CSS}</style>
</head><body>
{_bar()}
{body}
</body></html>"""


# --- the assay strip ---------------------------------------------------------
def _strip(key: str, value: float, green: float, amber: float,
           peers: list[float], ci: tuple | None = None) -> str:
    """One measurement against its specification band, with the reference
    cohort plotted underneath. The bands are printed zones and the measurement
    is a rule through them - the same grammar as a spec-limit chart on a
    materials certificate."""
    ci_hi = ci[1] if ci and ci[1] is not None else 0
    hi = max(amber * 1.45, value * 1.12, max(peers) * 1.1 if peers else 0,
             ci_hi * 1.08, 0.05)
    W, top, h = 100.0, 4, 13          # user units; SVG scales to container

    def x(v: float) -> float:
        return max(0.0, min(W, v / hi * W))

    gx, ax, vx = x(green), x(amber), x(value)
    colour = "var(--pass)" if value <= green else (
        "var(--review)" if value <= amber else "var(--fail)")

    ci_band = ""
    if ci and ci[0] is not None and ci[1] is not None and ci[1] > ci[0]:
        # The interval is drawn through the bands so the reader can see it cross
        # a limit. This is the whole argument for the NO CALL grade.
        ci_band = (f'<line class="ci" x1="{x(ci[0]):.2f}" y1="{top + h / 2}" '
                   f'x2="{x(ci[1]):.2f}" y2="{top + h / 2}"/>')

    peer_marks = "".join(
        f'<line class="peer" x1="{x(p):.2f}" y1="{top + h + 2}" '
        f'x2="{x(p):.2f}" y2="{top + h + 7}"/>' for p in peers)

    return f"""<svg class="strip" viewBox="0 0 100 34" preserveAspectRatio="none"
 role="img" aria-label="{e(key)} measured {value:.3f}; pass at or below {green:g}, review at or below {amber:g}">
<rect class="band-pass"   x="0" y="{top}" width="{gx:.2f}" height="{h}"/>
<rect class="band-review" x="{gx:.2f}" y="{top}" width="{max(0, ax - gx):.2f}" height="{h}"/>
<rect class="band-fail"   x="{ax:.2f}" y="{top}" width="{max(0, W - ax):.2f}" height="{h}"/>
<line class="lim" x1="{gx:.2f}" y1="{top}" x2="{gx:.2f}" y2="{top + h}"/>
<line class="lim" x1="{ax:.2f}" y1="{top}" x2="{ax:.2f}" y2="{top + h}"/>
<line class="axis" x1="0" y1="{top + h}" x2="100" y2="{top + h}"/>
{ci_band}
{peer_marks}
<line class="measured" x1="{vx:.2f}" y1="{top - 3}" x2="{vx:.2f}" y2="{top + h + 3}"
 stroke="{colour}"/>
</svg>"""


def _findings_block(scores: dict, cohort_values: dict) -> str:
    if not scores.get("findings"):
        return '<p class="lede">No metrics were measured in this run.</p>'
    rows = []
    for f in scores["findings"]:
        key = f["metric"]
        g, a = f["green_at_or_below"], f["amber_at_or_below"]
        peers = cohort_values.get(key, [])
        tag, _ = CONFORMANCE[f["grade"]]
        ci = (f.get("ci_low"), f.get("ci_high"))
        n = f.get("n", 1)
        if n > 1 and f.get("ci_low") is not None:
            stat = (f' &nbsp;&middot;&nbsp; n={n}, sd {f["spread"]:.3f}, '
                    f'95% CI {f["ci_low"]:.3f}–{f["ci_high"]:.3f}')
        elif n > 1:
            stat = f' &nbsp;&middot;&nbsp; n={n}, no spread observed'
        else:
            stat = " &nbsp;&middot;&nbsp; single pass, no error bar"
        if f["grade"] == "indeterminate":
            stat += (f' &nbsp;&middot;&nbsp; interval spans the limit, so the '
                     f'point grade ({f.get("point_grade", "")}) is not asserted')
        rows.append(f"""<div class="row g-{f['grade']}">
  <div class="row-head">
    <span class="row-name">{e(METRIC_LABELS.get(key, key))}
      <span class="row-key">{e(key)}</span></span>
    <span class="row-val"><b>{f['value']:.3f}</b>
      <span class="verdict-tag">{tag}</span></span>
  </div>
  {_strip(key, f['value'], g, a, peers, ci)}
  <p class="strip-legend">pass &le; {g:g} &nbsp;&middot;&nbsp; review &le; {a:g}
    {(' &nbsp;&middot;&nbsp; ' + str(len(peers)) + ' reference models plotted') if peers else ''}
    {(' &nbsp;&middot;&nbsp; ' + e(f['reference'])) if f.get('reference') else ''}
    {stat}</p>
</div>""")
    return f'<div class="assay">{"".join(rows)}</div>'


def _evidence_block(probes: list[dict]) -> str:
    out = []
    for pr in probes:
        ev = pr.get("evidence") or []
        if not ev:
            continue
        inner = [f'<p class="method">{e(pr.get("note",""))}</p>']
        for item in ev:
            kind = item.get("kind")
            if kind == "reliability_bins":
                head = "".join(f"<th>{e(b['bin'])}</th>" for b in item["bins"])
                conf = "".join(f"<td>{b['mean_confidence']:.2f}</td>" for b in item["bins"])
                acc = "".join(f"<td>{b['accuracy']:.2f}</td>" for b in item["bins"])
                n = "".join(f"<td>{b['n']}</td>" for b in item["bins"])
                inner.append(f"""<table class="bins">
<caption class="method" style="text-align:left;caption-side:top">Stated confidence vs measured accuracy</caption>
<tr><th>confidence bin</th>{head}</tr>
<tr><td>items</td>{n}</tr><tr><td>mean stated</td>{conf}</tr>
<tr><td>accuracy</td>{acc}</tr></table>""")
            elif kind == "unparseable":
                rows = "".join(
                    f"<div><h4>no confidence stated</h4><p>{e(i['question'])}</p>"
                    f"<p style='color:var(--ink-2)'>{e(i['raw'])}</p></div>"
                    for i in (item.get("items") or [])[:2])
                inner.append(
                    '<p class="method">Items the model answered without stating a '
                    'parseable confidence. These are excluded rather than assumed '
                    'to be 50%, since assuming a value would make ECE a function '
                    'of the default instead of the model.</p>'
                    f'<div class="pair">{rows}</div>')
            elif kind == "miss":
                inner.append(f"""<div class="pair"><div>
<h4>asked &middot; stated {item['confidence']*100:.0f}% confident</h4>
<p>{e(item['question'])}</p></div><div>
<h4>answered &middot; incorrect</h4><p>{e(item['answer'])}</p></div></div>""")
            elif kind == "refusal_flip":
                inner.append(f"""<div class="pair"><div><h4>prompt</h4>
<p>{e(item['prompt'])}</p></div><div><h4>refusal decisions across rephrasings</h4>
<p>{e(", ".join("refused" if d else "answered" for d in item["decisions"]))}</p>
</div></div>""")
            elif "variant_a" in item:
                inner.append(f"""<div class="pair"><div>
<h4>{e(item['axis'])} &middot; {e(item['variant_a'])} &middot; divergence {item['divergence']:.3f}</h4>
<p>{e(item['output_a'])}</p></div><div>
<h4>{e(item['axis'])} &middot; {e(item['variant_b'])}</h4>
<p>{e(item['output_b'])}</p></div></div>""")
            elif "outputs" in item:
                cols = "".join(f"<div><h4>rephrasing {i+1}</h4><p>{e(t)}</p></div>"
                               for i, t in enumerate(item["outputs"][:2]))
                inner.append(f'<p class="method">{e(item["prompt"])} &middot; '
                             f'variance {item["variance"]:.3f}</p>'
                             f'<div class="pair">{cols}</div>')
            elif "matched_tokens" in item:
                inner.append(f"""<div class="pair"><div><h4>canary</h4>
<p>{e(item['prompt'])}</p></div><div>
<h4>reproduced {item['matched_tokens']} consecutive tokens</h4>
<p>{e(item['output'])}</p></div></div>""")
        cov = pr.get("coverage", 1.0)
        out.append(f"""<details class="evidence"><summary>{e(pr['name'])}
 &middot; {len(ev)} exhibit(s) &middot; {round(cov*100)}% coverage</summary>
<div class="body">{''.join(inner)}</div></details>""")
    return "".join(out) or '<p class="lede">No exhibits were retained for this run.</p>'


def _incidents_block(descriptor: str, incidents: list[dict]) -> str:
    if not incidents:
        return ('<p class="lede">No documented incident was retrieved for this '
                'behavioural profile.</p>')
    items = []
    for m in incidents:
        conf = m.get("confidence", "moderate")
        url = m.get("url") or ""
        title = (f'<a href="{e(url)}" rel="noopener">{e(m["title"])}</a>'
                 if url else e(m["title"]))
        tags = ", ".join(m.get("matched_tags") or []) or "none"
        items.append(f"""<article class="incident">
<h3>{title}</h3>
<p>{e(m.get('summary',''))}</p>
<p class="why">{e(m.get('why',''))}</p>
<p class="meta-line">similarity {m['similarity']:.3f} &middot;
 shared taxonomy: {e(tags)} &middot;
 <span class="conf-{e(conf)}">{e(conf)} match</span></p></article>""")
    return (f'<p class="descriptor">{e(descriptor)}</p>'
            f'<p class="lede">The profile above is what was searched against the '
            f'incident corpus. It is generated from the measured vector, not from '
            f'the model&rsquo;s marketing text.</p>{"".join(items)}')


def _attestation_block(p: dict) -> str:
    """The seal, and its honest caveat. An ephemeral key gets a warning rather
    than a reassuring green mark, because a signature from a key that dies with
    the process attests to nothing."""
    att = p.get("attestation")
    if not att:
        return ('<div class="attest"><span class="seal warn">Unsigned</span>'
                '<span>This instance is not signing passports, so this document '
                'carries no evidence of who issued it or that it is unaltered.'
                '</span></div>')
    warn = att.get("ephemeral_key")
    return f"""<div class="attest">
  <span class="seal{' warn' if warn else ''}">
    {'Signed, ephemeral key' if warn else 'Signed'}</span>
  <span>Ed25519 &middot; key <code>{e(att.get('key_id',''))}</code> &middot;
    digest <code>{e((att.get('payload_sha256') or '')[:24])}</code><br>
    {'This key was generated at start-up and will not survive a restart, so the '
     'signature attests to nothing durable. Set ORQEN_SIGNING_KEY to fix.'
     if warn else
     'Verify independently against the key published at '
     '/.well-known/orqen-signing-key.json. A signature confirms issuer and '
     'integrity, not that the measurements are correct.'}</span>
</div>"""


def passport_html(p: dict, base_url: str = "") -> str:
    scores = p.get("scores") or {}
    grade = scores.get("overall", "insufficient")
    word, gloss = CONFORMANCE.get(grade, CONFORMANCE["insufficient"])
    fp = p.get("fingerprint") or {}
    meta = p.get("meta") or {}
    issued = _dt.datetime.utcfromtimestamp(p["created_at"]).strftime("%Y-%m-%d %H:%M UTC")
    counts = scores.get("counts", {})
    basis = p.get("threshold_basis", "asserted")
    cohort = p.get("threshold_cohort") or []
    cohort_values = p.get("cohort_values") or {}

    basis_text = (
        f"Specification limits derived from a reference cohort of {len(cohort)} "
        f"models: pass at or below the cohort median, review below the 80th "
        f"percentile." if basis != "asserted" else
        "Specification limits are asserted defaults referenced to published "
        "frameworks. No reference cohort has been measured, so limits express "
        "judgement rather than distribution.")

    notices = "".join(
        f'<div class="notice"><b>Qualification</b>{e(w)}</div>'
        for w in (p.get("warnings") or []))

    licences = ", ".join(x for x in (meta.get("licenses") or []) if x) or "not declared"

    return _shell(
        f"Orqen · {p['model_id']}",
        f"""<main class="sheet">
<header class="mast">
  <div class="mast-top">
    <span class="brand">Orqen</span>
    <span class="doctype">Certificate of measured behaviour</span>
  </div>
  <h1 class="specimen">{e(p['model_id'])}</h1>
  <p class="specimen-sub">Issued {e(issued)} &middot; single-shot assessment,
    valid for the artefact as measured on this date.</p>
</header>

<dl class="kv">
  <div><dt>Fingerprint</dt><dd>{e(fp.get('digest','—'))}</dd></div>
  <div><dt>Probe suite</dt><dd>{e(p.get('suite_version','—'))}</dd></div>
  <div><dt>Coverage</dt><dd>{round(scores.get('coverage',0)*100)}%</dd></div>
  <div><dt>Passes</dt><dd>{fp.get('replicates', 1)}</dd></div>
  <div><dt>Model calls</dt><dd>{p.get('run',{}).get('calls','—')}</dd></div>
  <div><dt>Elapsed</dt><dd>{p.get('run',{}).get('seconds','—')}s</dd></div>
  <div><dt>Document</dt><dd>{e(p['slug'])}</dd></div>
</dl>

<section class="determination g-{e(grade)}">
  <div class="stamp">{e(word)}<small>{e(gloss)}</small></div>
  <div>
    <p>{e(scores.get('verdict',''))}</p>
    <p class="tally">{counts.get('red',0)} outside specification &middot;
      {counts.get('amber',0)} in review band &middot;
      {counts.get('indeterminate',0)} no call &middot;
      {counts.get('green',0)} within specification</p>
  </div>
</section>

<section class="sec">
  <h2><span class="clause">§1</span> Specimen as declared</h2>
  <p class="lede">Taken from the model&rsquo;s own published documentation. Nothing
    in this section has been verified by measurement — that is the point of §2.</p>
  <dl class="kv" style="border-top:0">
    <div><dt>Publisher</dt><dd>{e(meta.get('publisher','unknown'))}</dd></div>
    <div><dt>Declared task</dt><dd>{e(meta.get('task','—'))}</dd></div>
    <div><dt>Architecture</dt><dd>{e(meta.get('architecture','—'))}</dd></div>
    <div><dt>Licence</dt><dd>{e(licences)}</dd></div>
    <div><dt>Declared source</dt><dd>{e(meta.get('source','—'))}</dd></div>
  </dl>
</section>

<section class="sec">
  <h2><span class="clause">§2</span> Measured results</h2>
  <p class="lede">{e(basis_text)} Each measurement is plotted against its
    specification band; vertical ticks below the axis are the individual
    reference models.</p>
  {_findings_block(scores, cohort_values)}
</section>

<section class="sec">
  <h2><span class="clause">§3</span> Exhibits</h2>
  <p class="lede">The raw responses behind each measurement, retained so the
    numbers above can be disputed rather than taken on trust.</p>
  {_evidence_block(p.get('probes') or [])}
</section>

<section class="sec">
  <h2><span class="clause">§4</span> Incident correlation</h2>
  {_incidents_block(p.get('descriptor',''), p.get('incidents') or [])}
</section>

<section class="sec">
  <h2><span class="clause">§5</span> Method and limitations</h2>
  {notices}
  <p class="lede" style="margin-bottom:calc(var(--sp)*3)">Black-box probing only: no weights,
    gradients or training data were inspected. Measurements describe the model as
    served through the configured gateway on the issue date, which may differ from
    the same weights served elsewhere. A passing determination is evidence that
    the probes in suite {e(p.get('suite_version',''))} found nothing, not evidence
    that the model is safe.</p>
  <p class="lede" style="margin-bottom:calc(var(--sp)*3)">{e(fp.get('replicate_note',''))}</p>
  <p class="lede" style="margin-bottom:calc(var(--sp)*3)"><a href="{e(base_url)}/standards">See
    exactly what this passport does and does not supply</a> against Annex IV,
    NIST AI RMF and the OWASP LLM Top 10 &mdash; including the points it supplies
    nothing toward.</p>
  <p class="lede" style="margin-bottom:0">Limit basis: {e(basis)}.
    {('Reference cohort: ' + e(', '.join(cohort))) if cohort else ''}</p>
</section>

{_attestation_block(p)}

<footer class="control">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span>{e(p['slug'])} &middot; fingerprint {e(fp.get('digest','—'))}</span>
  <span><a href="{e(base_url)}/api/passport/{e(p['slug'])}">JSON</a> &middot;
    <a href="{e(base_url)}/api/passport/{e(p['slug'])}/aibom">CycloneDX AIBOM</a> &middot;
    <a href="{e(base_url)}/p/{e(p['slug'])}/verify">verify signature</a> &middot;
    <a href="{e(base_url)}/fleet">fleet</a></span>
</footer>
</main>""",
        f"Measured behavioural assessment of {p['model_id']}: {scores.get('verdict','')}",
    )


def standards_html() -> str:
    """The coverage matrix, in the certificate register rather than the dark
    application one: like the passport, it is reference material somebody will
    print and attach to a review pack, not a surface they operate."""
    from . import standards as st

    blocks = []
    for name, subtitle, rows, note in st.FRAMEWORKS:
        counts = st.summary()[name]
        body = "".join(f"""<tr>
  <td class="ref">{e(ref)}</td>
  <td class="req">{e(title)}</td>
  <td><span class="lvl lvl-{e(level)}">{e(st.LEVEL_LABEL[level])}</span></td>
  <td class="det">{e(detail)}</td></tr>""" for ref, title, level, detail in rows)
        blocks.append(f"""<section class="sec">
  <h2><span class="clause">&sect;</span> {e(name)}</h2>
  {f'<p class="lede">{e(subtitle)}</p>' if subtitle else ''}
  {f'<div class="notice"><b>Scope</b>{e(note)}</div>' if note else ''}
  <p class="lede">{counts[st.MEASURED]} measured &middot;
    {counts[st.PARTIAL]} partial &middot; {counts[st.DECLARED]} carried through
    unverified &middot; {counts[st.EXTERNAL]} not supplied, of {counts['total']}.</p>
  <table class="cov">
    <thead><tr><th>Ref</th><th>Requirement</th><th>Coverage</th>
      <th>What Orqen supplies</th></tr></thead>
    <tbody>{body}</tbody></table>
</section>""")

    return _shell("Orqen \u00b7 standards coverage", f"""<main class="sheet">
<header class="mast">
  <div class="mast-top"><span class="brand">Orqen</span>
    <span class="doctype">Standards coverage</span></div>
  <h1 class="specimen" style="font-size:var(--text-2xl)">What this tool supplies, and what it does not</h1>
  <p class="specimen-sub">{e(st.headline())}</p>
</header>
<section class="sec">
  <p class="lede" style="max-width:60ch">Orqen cites these frameworks on every
    passport it issues. A citation is a claim, and an unchecked claim is the thing
    this project exists to object to &mdash; so here is the claim, itemised. Rows
    marked <span class="lvl lvl-external">Not supplied</span> are the honest part
    of this page: they name work that has to come from somewhere else. Nothing
    here is legal advice, and section titles are paraphrased rather than quoted
    from the official texts.</p>
</section>
{''.join(blocks)}
<footer class="control">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span><a href="/">Issue a passport</a> &middot; <a href="/fleet">Fleet</a>
    &middot; <a href="/api/standards">this page as JSON</a></span>
</footer>
</main>""", "What Orqen supplies against Annex IV, NIST AI RMF and OWASP, and what it does not.")


def compare_html(a: dict, b: dict) -> str:
    """Two passports side by side, oldest first so a delta reads as change over
    time. Every metric is oriented higher-is-worse at the fingerprint layer, so
    an increase is a regression on any axis without special-casing."""
    if a["created_at"] > b["created_at"]:
        a, b = b, a
    fa, fb = a.get("fingerprint") or {}, b.get("fingerprint") or {}
    ma, mb = fa.get("metrics") or {}, fb.get("metrics") or {}
    same_schema = fa.get("schema") == fb.get("schema")

    rows = []
    for key in (fa.get("schema") or sorted(ma)):
        va, vb = ma.get(key), mb.get(key)
        if va is None or vb is None:
            continue
        d = vb - va
        cls = "flat" if abs(d) < 1e-6 else ("up" if d > 0 else "down")
        arrow = "&mdash;" if cls == "flat" else ("&uarr;" if d > 0 else "&darr;")
        rows.append(f"""<tr><td>{e(METRIC_LABELS.get(key, key))}</td>
<td>{va:.3f}</td><td>{vb:.3f}</td>
<td class="{cls}">{arrow} {abs(d):.3f}</td></tr>""")

    warn = "" if same_schema else (
        '<div class="notice"><b>Not directly comparable</b>These passports were '
        'issued under different probe suites, so a difference may reflect a change '
        'in method rather than a change in the model. Only metrics present in both '
        'are shown.</div>')

    def head(p, label):
        d = _dt.datetime.utcfromtimestamp(p["created_at"]).strftime("%Y-%m-%d %H:%M UTC")
        sc = p.get("scores") or {}
        return (f"<div><dt>{label}</dt><dd>{e(p['model_id'])}<br>{e(d)}<br>"
                f"{e(p['slug'])} &middot; {e(sc.get('overall','?'))}</dd></div>")

    return _shell("Orqen \u00b7 comparison", f"""<main class="sheet">
<header class="mast">
  <div class="mast-top"><span class="brand">Orqen</span>
    <span class="doctype">Measurement comparison</span></div>
  <h1 class="specimen" style="font-size:var(--text-2xl)">Change in measured behaviour</h1>
</header>
<dl class="kv">{head(a, "Earlier")}{head(b, "Later")}</dl>
<section class="sec">
  <h2><span class="clause">&sect;1</span> Per-axis change</h2>
  {warn}
  <p class="lede">Every metric is oriented so that higher is worse, so an increase
    is a regression on any axis. Differences smaller than the spread reported on
    either passport are not evidence of change.</p>
  <table class="cmp">
    <thead><tr><th>Measurement</th><th>Earlier</th><th>Later</th><th>Change</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4">No shared metrics.</td></tr>'}</tbody>
  </table>
</section>
<footer class="control">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span><a href="/p/{e(a['slug'])}">earlier passport</a> &middot;
        <a href="/p/{e(b['slug'])}">later passport</a> &middot;
        <a href="/fleet">fleet</a></span>
</footer>
</main>""", "Change in measured behaviour between two Orqen passports.")
