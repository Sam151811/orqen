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

CSS = """
:root{
  --paper:#EEF0F2;        /* cool lab-stock ground */
  --sheet:#FCFCFD;
  --ink:#14181D;
  --ink-2:#4A525C;
  --rule:#C9D0D6;
  --rule-hair:#DFE4E8;
  --slate:#2E4A62;        /* structural accent, ink not neon */
  --pass:#1F6F5C;
  --review:#8A5A00;
  --fail:#A3282C;
  --none:#5A5F6A;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--paper);color:var(--ink);
  font-family:"Source Serif 4",Georgia,serif;font-size:16px;line-height:1.55;
}
.wrap{max-width:60rem;margin:0 auto;padding:2rem 1.25rem 5rem}
.sheet{
  background:var(--sheet);border:1px solid var(--rule);
  box-shadow:0 1px 0 rgba(20,24,29,.04);
}

/* ---- masthead ---- */
.mast{border-bottom:2px solid var(--ink);padding:1.5rem 1.75rem 1.25rem}
.mast-top{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;flex-wrap:wrap}
.brand{
  font-family:Archivo,system-ui,sans-serif;font-weight:700;
  letter-spacing:.22em;text-transform:uppercase;font-size:.8rem;color:var(--slate);
}
.doctype{
  font-family:Archivo,system-ui,sans-serif;font-size:.7rem;letter-spacing:.16em;
  text-transform:uppercase;color:var(--ink-2);
}
.specimen{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:1.6rem;
  font-weight:500;margin:.85rem 0 0;word-break:break-word;line-height:1.2;
}
.specimen-sub{font-size:.9rem;color:var(--ink-2);margin:.3rem 0 0}

/* ---- key/value grids ---- */
.kv{
  display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));
  gap:0;border-top:1px solid var(--rule-hair);
}
.kv > div{
  padding:.7rem 1.75rem;border-bottom:1px solid var(--rule-hair);
  border-right:1px solid var(--rule-hair);
}
.kv dt{
  font-family:Archivo,system-ui,sans-serif;font-size:.62rem;letter-spacing:.13em;
  text-transform:uppercase;color:var(--ink-2);margin:0 0 .2rem;
}
.kv dd{
  margin:0;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.82rem;word-break:break-word;
}

/* ---- determination ---- */
.determination{display:flex;gap:1.5rem;align-items:flex-start;padding:1.5rem 1.75rem;
  border-bottom:1px solid var(--rule)}
.stamp{
  flex:0 0 auto;border:2px solid currentColor;padding:.5rem .9rem;
  font-family:Archivo,system-ui,sans-serif;font-weight:700;font-size:1.05rem;
  letter-spacing:.1em;text-transform:uppercase;line-height:1.1;
}
.stamp small{display:block;font-size:.55rem;letter-spacing:.12em;font-weight:600;
  opacity:.75;margin-top:.25rem}
.g-green,.g-green .stamp{color:var(--pass)}
.g-amber,.g-amber .stamp{color:var(--review)}
.g-red,.g-red .stamp{color:var(--fail)}
.g-insufficient,.g-insufficient .stamp{color:var(--none)}
.g-indeterminate,.g-indeterminate .stamp{color:var(--slate)}
.strip .ci{stroke:var(--ink-2);stroke-width:5;opacity:.28;stroke-linecap:butt}
.determination p{margin:.1rem 0 0;color:var(--ink);font-size:1.02rem}
.tally{margin:.55rem 0 0;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.76rem;color:var(--ink-2)}

/* ---- sections ---- */
.sec{padding:1.6rem 1.75rem;border-bottom:1px solid var(--rule-hair)}
.sec:last-child{border-bottom:0}
.sec > h2{
  font-family:Archivo,system-ui,sans-serif;font-size:.72rem;letter-spacing:.15em;
  text-transform:uppercase;color:var(--slate);margin:0 0 1rem;
  display:flex;align-items:baseline;gap:.65rem;
}
.sec > h2 .clause{
  font-family:"IBM Plex Mono",ui-monospace,monospace;color:var(--ink-2);
  font-size:.72rem;letter-spacing:0;
}
.sec > h2::after{content:"";flex:1;height:1px;background:var(--rule-hair)}
.lede{margin:-.35rem 0 1.15rem;color:var(--ink-2);font-size:.92rem;max-width:44rem}

/* ---- assay strips: the signature element ---- */
.assay{border-top:1px solid var(--rule-hair)}
.row{padding:.95rem 0;border-bottom:1px solid var(--rule-hair)}
.row-head{display:flex;justify-content:space-between;align-items:baseline;gap:1rem;
  margin-bottom:.5rem;flex-wrap:wrap}
.row-name{font-size:.95rem}
.row-key{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--ink-2);display:block}
.row-val{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:1rem;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.row-val b{font-weight:600}
.verdict-tag{font-family:Archivo,system-ui,sans-serif;font-size:.6rem;font-weight:700;
  letter-spacing:.1em;padding:.12rem .4rem;border:1px solid currentColor;margin-left:.5rem}
.strip{width:100%;height:34px;display:block;overflow:visible}
.strip .band-pass{fill:var(--pass);opacity:.13}
.strip .band-review{fill:var(--review);opacity:.15}
.strip .band-fail{fill:var(--fail);opacity:.12}
.strip .axis{stroke:var(--rule);stroke-width:1}
.strip .peer{stroke:var(--ink-2);stroke-width:1;opacity:.5}
.strip .measured{stroke-width:2.5}
.strip .lim{stroke:var(--ink-2);stroke-width:1;stroke-dasharray:2 2}
.strip text{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:8.5px;
  fill:var(--ink-2)}
.strip-legend{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.66rem;
  color:var(--ink-2);margin:.3rem 0 0}
@media (prefers-reduced-motion:no-preference){
  .strip .measured{transform-origin:left;animation:mark .5s ease-out both}
  @keyframes mark{from{opacity:0}to{opacity:1}}
}

/* ---- evidence ---- */
.evidence{border:1px solid var(--rule-hair);margin:0 0 .8rem}
.evidence > summary{
  cursor:pointer;padding:.6rem .8rem;font-family:Archivo,system-ui,sans-serif;
  font-size:.74rem;letter-spacing:.06em;text-transform:uppercase;
  background:#F4F6F7;
}
.evidence > summary:focus-visible{outline:2px solid var(--slate);outline-offset:2px}
.evidence .body{padding:.8rem;border-top:1px solid var(--rule-hair)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;margin:0 0 .9rem}
.pair > div{border-left:2px solid var(--rule);padding-left:.65rem}
.pair h4{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--ink-2);margin:0 0 .25rem;font-weight:500}
.pair p{margin:0;font-size:.86rem}
.method{font-size:.85rem;color:var(--ink-2);margin:.1rem 0 .8rem}
table.bins{border-collapse:collapse;width:100%;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.76rem;margin:.2rem 0 .6rem}
table.bins th,table.bins td{border:1px solid var(--rule-hair);padding:.3rem .5rem;
  text-align:right;font-variant-numeric:tabular-nums}
table.bins th{text-align:right;font-weight:500;color:var(--ink-2);background:#F4F6F7}
table.bins td:first-child,table.bins th:first-child{text-align:left}

/* ---- incidents ---- */
.descriptor{border-left:3px solid var(--slate);padding:.1rem 0 .1rem .9rem;
  margin:0 0 1.2rem;font-size:.95rem}
.incident{border-top:1px solid var(--rule-hair);padding:.9rem 0}
.incident h3{margin:0 0 .3rem;font-size:1rem;font-weight:600}
.incident h3 a{color:var(--ink);text-decoration-color:var(--rule)}
.incident p{margin:.25rem 0;font-size:.88rem;color:var(--ink-2)}
.incident .why{color:var(--ink);font-size:.86rem}
.meta-line{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--ink-2);margin:.3rem 0 0}
.conf-strong{color:var(--pass)}.conf-moderate{color:var(--review)}.conf-weak{color:var(--none)}

/* ---- notices ---- */
.notice{border:1px solid var(--review);border-left-width:3px;padding:.6rem .8rem;
  margin:0 0 .6rem;font-size:.86rem;color:var(--ink)}
.notice b{font-family:Archivo,system-ui,sans-serif;font-size:.62rem;letter-spacing:.1em;
  text-transform:uppercase;color:var(--review);display:block;margin-bottom:.15rem}

/* ---- attestation ---- */
.attest{display:flex;gap:1rem;align-items:flex-start;padding:1rem 1.75rem;
  border-top:1px solid var(--rule-hair);background:#F7F9F9;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.7rem;
  color:var(--ink-2);flex-wrap:wrap}
.attest .seal{border:1px solid var(--pass);color:var(--pass);padding:.2rem .45rem;
  font-family:Archivo,system-ui,sans-serif;font-size:.58rem;letter-spacing:.1em;
  text-transform:uppercase;white-space:nowrap}
.attest .seal.warn{border-color:var(--review);color:var(--review)}
.attest code{word-break:break-all}

/* ---- coverage matrix ---- */
.cov{border-collapse:collapse;width:100%;font-size:.86rem;margin:0 0 2rem}
.cov th{text-align:left;font-family:Archivo,system-ui,sans-serif;font-size:.6rem;
  letter-spacing:.13em;text-transform:uppercase;color:var(--ink-2);
  padding:0 .8rem .5rem 0;border-bottom:1px solid var(--rule)}
.cov td{padding:.75rem .8rem .75rem 0;border-bottom:1px solid var(--rule-hair);
  vertical-align:top}
.cov td.ref{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.76rem;
  white-space:nowrap;color:var(--ink-2)}
.cov td.req{font-weight:600}
.cov td.det{color:var(--ink-2);font-size:.84rem}
.lvl{font-family:Archivo,system-ui,sans-serif;font-size:.58rem;letter-spacing:.09em;
  text-transform:uppercase;padding:.14rem .4rem;border:1px solid currentColor;
  white-space:nowrap;display:inline-block}
.lvl-measured{color:var(--pass)}.lvl-declared{color:var(--slate)}
.lvl-partial{color:var(--review)}.lvl-external{color:var(--none)}

/* ---- comparison ---- */
.cmp{border-collapse:collapse;width:100%;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.82rem}
.cmp th{text-align:right;font-size:.6rem;letter-spacing:.12em;text-transform:uppercase;
  color:var(--ink-2);font-family:Archivo,system-ui,sans-serif;font-weight:600;
  padding:0 .7rem .6rem;border-bottom:1px solid var(--rule)}
.cmp th:first-child{text-align:left}
.cmp td{padding:.6rem .7rem;border-bottom:1px solid var(--rule-hair);text-align:right;
  font-variant-numeric:tabular-nums}
.cmp td:first-child{text-align:left;font-size:.78rem}
.cmp .up{color:var(--fail)}.cmp .down{color:var(--pass)}.cmp .flat{color:var(--ink-2)}

/* ---- footer / document control ---- */
.control{padding:1.1rem 1.75rem;background:#F4F6F7;border-top:2px solid var(--ink);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;color:var(--ink-2);
  display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.control a{color:var(--slate)}

/* ---- landing ---- */
.hero{padding:3.5rem 1.75rem 2.5rem;text-align:left}
.hero .brand{display:block;margin-bottom:1.4rem}
.hero h1{font-family:Archivo,system-ui,sans-serif;font-size:clamp(1.9rem,5vw,3rem);
  line-height:1.08;margin:0 0 .8rem;letter-spacing:-.015em;max-width:22ch}
.hero .claim{font-size:1.05rem;color:var(--ink-2);max-width:46ch;margin:0 0 2rem}
.hero .claim em{font-style:normal;color:var(--ink);border-bottom:1px solid var(--slate)}
form.audit{display:flex;gap:.5rem;flex-wrap:wrap;max-width:34rem}
form.audit input{
  flex:1 1 18rem;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.92rem;
  padding:.7rem .8rem;border:1px solid var(--ink);background:var(--sheet);color:var(--ink);
}
form.audit input:focus-visible{outline:2px solid var(--slate);outline-offset:1px}
form.audit button{
  font-family:Archivo,system-ui,sans-serif;font-weight:600;font-size:.8rem;
  letter-spacing:.1em;text-transform:uppercase;padding:.7rem 1.3rem;cursor:pointer;
  background:var(--ink);color:var(--sheet);border:1px solid var(--ink);
}
form.audit button:hover{background:var(--slate);border-color:var(--slate)}
form.audit button:focus-visible{outline:2px solid var(--slate);outline-offset:2px}
.eg{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.74rem;
  color:var(--ink-2);margin:.7rem 0 0}
.eg a{color:var(--slate)}

@media (max-width:640px){
  .determination{flex-direction:column;gap:.9rem}
  .pair{grid-template-columns:1fr}
  .kv > div{padding-left:1rem;padding-right:1rem}
  .sec,.mast,.determination,.control,.hero{padding-left:1rem;padding-right:1rem}
}
@media print{
  body{background:#fff}
  .wrap{max-width:none;padding:0}
  .sheet{border:0;box-shadow:none}
  .evidence[open] > summary{display:none}
  .evidence{border-color:#ccc}
  details{break-inside:avoid}
  .row{break-inside:avoid}
}
"""

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
         'family=Archivo:wght@400;600;700&family=IBM+Plex+Mono:wght@400;500;600&'
         'family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">')


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _shell(title: str, body: str, desc: str = "") -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
{FONTS}
<style>{CSS}</style>
</head><body><div class="wrap">{body}</div></body></html>"""


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
  <p class="lede" style="margin-bottom:.6rem">Black-box probing only: no weights,
    gradients or training data were inspected. Measurements describe the model as
    served through the configured gateway on the issue date, which may differ from
    the same weights served elsewhere. A passing determination is evidence that
    the probes in suite {e(p.get('suite_version',''))} found nothing, not evidence
    that the model is safe.</p>
  <p class="lede" style="margin-bottom:.6rem">{e(fp.get('replicate_note',''))}</p>
  <p class="lede" style="margin-bottom:.6rem"><a href="{e(base_url)}/standards">See
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
  <span><a href="{e(base_url)}/api/passport/{e(p['slug'])}">machine-readable JSON</a>
   &middot; <a href="{e(base_url)}/api/passport/{e(p['slug'])}/aibom">CycloneDX AIBOM</a></span>
</footer>
</main>""",
        f"Measured behavioural assessment of {p['model_id']}: {scores.get('verdict','')}",
    )



# =============================================================================
# Landing page
#
# Deliberately the inverse of the passport. The passport is pale lab stock - a
# document of record, printed. The landing page is the instrument that produced
# it: cold, dark, backlit. Two registers, one system, rather than two templates
# sharing a logo.
#
# Its own type and colour tokens, and its own class prefix (.lp-), so nothing
# here can collide with the certificate CSS above.
# =============================================================================

LANDING_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Instrument+Serif:ital@0;1&'
    'family=IBM+Plex+Mono:wght@400;500&'
    'family=IBM+Plex+Sans:wght@400;500&display=swap">'
)

LANDING_CSS = """
:root{
  --lp-ground:#0A0D11;      /* cold near-black, blue cast - instrument housing */
  --lp-raised:#111620;
  --lp-ink:#E8ECEF;         /* cool white */
  --lp-dim:#7E8B99;
  --lp-dimmer:#4C5865;
  --lp-rule:#1C232E;
  --lp-signal:#F0A93B;      /* sodium warning lamp. The page's only colour, and
                               it means exactly one thing: this was measured. */
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{
  margin:0;background:var(--lp-ground);color:var(--lp-ink);
  font-family:"IBM Plex Sans",system-ui,sans-serif;font-size:16px;line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.lp-mono{font-family:"IBM Plex Mono",ui-monospace,monospace}

/* type roles ------------------------------------------------------------- */
.lp-stmt{
  font-family:"Instrument Serif",Georgia,serif;font-weight:400;
  font-size:clamp(2.3rem,6.2vw,4.6rem);line-height:1.02;
  letter-spacing:-.015em;margin:0;
}
.lp-stmt em{font-style:italic;color:var(--lp-ink)}
.lp-stmt .lp-quiet{color:var(--lp-dimmer)}
.lp-eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.66rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--lp-dim);
  margin:0 0 1.1rem;
}
.lp-body{color:var(--lp-dim);font-size:1.02rem;max-width:46ch;margin:1.1rem 0 0}
.lp-body strong{color:var(--lp-ink);font-weight:500}

/* frame ------------------------------------------------------------------ */
.lp-shell{max-width:74rem;margin:0 auto;padding:0 1.5rem}
.lp-nav{
  position:sticky;top:0;z-index:10;backdrop-filter:blur(14px);
  background:rgba(10,13,17,.82);border-bottom:1px solid var(--lp-rule);
}
.lp-nav .lp-shell{display:flex;justify-content:space-between;align-items:center;
  height:3.4rem;gap:1rem}
.lp-wordmark{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.8rem;
  letter-spacing:.28em;text-transform:uppercase}
.lp-nav ul{display:flex;gap:1.5rem;list-style:none;margin:0;padding:0}
.lp-nav a{
  font-family:"Instrument Serif",Georgia,serif;font-style:italic;font-size:1rem;
  color:var(--lp-dim);text-decoration:none;
}
.lp-nav a:hover,.lp-nav a:focus-visible{color:var(--lp-ink)}
.lp-nav li:last-child a{color:var(--lp-signal)}
@media (max-width:720px){.lp-nav ul li:not(:last-child){display:none}}

.lp-sec{padding:5.5rem 0;border-bottom:1px solid var(--lp-rule)}
.lp-sec:last-of-type{border-bottom:0}
.lp-clause{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.66rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--lp-dimmer);
  display:block;margin:0 0 2.4rem;
}

/* hero ------------------------------------------------------------------- */
.lp-hero{padding:6rem 0 4.5rem}
.lp-hero .lp-stmt{max-width:24ch}
.lp-form{display:flex;gap:.5rem;flex-wrap:wrap;max-width:36rem;margin:2.6rem 0 0}
.lp-form label{
  flex:1 0 100%;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.66rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--lp-dim);margin-bottom:.55rem;
}
.lp-form input{
  flex:1 1 17rem;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.95rem;padding:.85rem .95rem;color:var(--lp-ink);
  background:var(--lp-raised);border:1px solid var(--lp-rule);border-radius:0;
}
.lp-form input::placeholder{color:var(--lp-dimmer)}
.lp-form input:focus-visible{outline:1px solid var(--lp-signal);outline-offset:-1px;
  border-color:var(--lp-signal)}
.lp-form button{
  font-family:"IBM Plex Sans",system-ui,sans-serif;font-weight:500;font-size:.9rem;
  padding:.85rem 1.5rem;cursor:pointer;border-radius:0;
  background:var(--lp-ink);color:var(--lp-ground);border:1px solid var(--lp-ink);
}
.lp-form button:hover{background:var(--lp-signal);border-color:var(--lp-signal)}
.lp-form button:focus-visible{outline:2px solid var(--lp-signal);outline-offset:2px}
.lp-try{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.74rem;
  color:var(--lp-dim);margin:.9rem 0 0}
.lp-try a{color:var(--lp-ink);text-decoration-color:var(--lp-dimmer);
  text-underline-offset:3px}
.lp-try a:hover{color:var(--lp-signal)}

/* SIGNATURE: the claim / measurement split -------------------------------
   The product's whole argument as one object. Top row is what the model card
   asserts, set in the register of an assertion. Bottom row is what the probes
   returned, set in the register of an instrument reading, against the same
   threshold scale the passport uses in §2. */
.lp-split{border:1px solid var(--lp-rule);background:var(--lp-raised)}
.lp-split-row{padding:1.9rem 1.8rem;display:grid;
  grid-template-columns:7.5rem 1fr;gap:1.8rem;align-items:start}
.lp-split-row + .lp-split-row{border-top:1px solid var(--lp-rule)}
.lp-split-tag{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.18em;text-transform:uppercase;color:var(--lp-dimmer);
  padding-top:.45rem;
}
.lp-declared{
  font-family:"Instrument Serif",Georgia,serif;font-style:italic;
  font-size:clamp(1.15rem,2.6vw,1.6rem);line-height:1.35;color:var(--lp-dim);
  margin:0;
}
.lp-source{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--lp-dimmer);margin:.7rem 0 0}
.lp-measured{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:clamp(1.05rem,2.4vw,1.4rem);line-height:1.35;margin:0;
  color:var(--lp-ink);
}
.lp-measured b{color:var(--lp-signal);font-weight:500}
.lp-figure{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:2.6rem;
  color:var(--lp-signal);line-height:1;margin:1.1rem 0 .1rem;
  font-variant-numeric:tabular-nums;
}
.lp-scale{width:100%;height:26px;display:block;margin:.5rem 0 0;overflow:visible}
.lp-scale .z1{fill:#1A2230}.lp-scale .z2{fill:#151C27}.lp-scale .z3{fill:#101620}
.lp-scale .axis{stroke:var(--lp-rule);stroke-width:1}
.lp-scale .lim{stroke:var(--lp-dimmer);stroke-width:1;stroke-dasharray:2 2}
.lp-scale .mark{stroke:var(--lp-signal);stroke-width:2.5}
.lp-scale text{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:7.5px;
  fill:var(--lp-dimmer)}

/* label / statement / body triad, after Pear's disclosure blocks --------- */
.lp-triad{display:grid;grid-template-columns:1fr 1fr;gap:3.5rem 4rem}
.lp-triad .lp-stmt{font-size:clamp(1.6rem,3.4vw,2.35rem);max-width:20ch}
@media (max-width:800px){.lp-triad{grid-template-columns:1fr;gap:2.8rem}}

/* method table ----------------------------------------------------------- */
.lp-probes{width:100%;border-collapse:collapse;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.82rem}
.lp-probes th{text-align:left;font-weight:400;color:var(--lp-dimmer);
  font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;
  padding:0 1rem .8rem 0;border-bottom:1px solid var(--lp-rule)}
.lp-probes td{padding:1rem 1rem 1rem 0;border-bottom:1px solid var(--lp-rule);
  vertical-align:top;color:var(--lp-dim)}
.lp-probes td:first-child{color:var(--lp-ink);white-space:nowrap}
.lp-probes td:last-child{color:var(--lp-ink);text-align:right;
  font-variant-numeric:tabular-nums;white-space:nowrap}
@media (max-width:720px){
  .lp-probes th:nth-child(2),.lp-probes td:nth-child(2){display:none}
}

/* plainly ---------------------------------------------------------------- */
.lp-plainly{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));
  gap:2.4rem}
.lp-plainly h3{font-family:"Instrument Serif",Georgia,serif;font-style:italic;
  font-weight:400;font-size:1.3rem;margin:0 0 .5rem;color:var(--lp-ink)}
.lp-plainly p{margin:0;color:var(--lp-dim);font-size:.94rem}

/* footer ----------------------------------------------------------------- */
.lp-foot{padding:3rem 0 4rem;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.7rem;color:var(--lp-dimmer);display:flex;justify-content:space-between;
  gap:1.5rem;flex-wrap:wrap}
.lp-foot a{color:var(--lp-dim)}

.lp-notice{border-left:2px solid var(--lp-signal);background:var(--lp-raised);
  padding:.85rem 1rem;margin:1.8rem 0 0;max-width:36rem;font-size:.9rem}
.lp-notice b{display:block;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.62rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--lp-signal);margin-bottom:.25rem}

/* standards strip --------------------------------------------------------
   The structural slot a marketing page fills with client logos. Orqen has no
   clients, so it carries the documents the numbers are referenced to instead.
   Every entry here is cited somewhere in a passport; none of it is decoration. */
.lp-strip{border-top:1px solid var(--lp-rule);border-bottom:1px solid var(--lp-rule);
  padding:1.4rem 0;overflow:hidden;position:relative}
.lp-strip::before,.lp-strip::after{content:"";position:absolute;top:0;bottom:0;
  width:5rem;z-index:2;pointer-events:none}
.lp-strip::before{left:0;background:linear-gradient(90deg,var(--lp-ground),transparent)}
.lp-strip::after{right:0;background:linear-gradient(270deg,var(--lp-ground),transparent)}
.lp-strip-label{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--lp-dimmer);
  margin:0 0 1.1rem}
.lp-track{display:flex;gap:3rem;width:max-content}
.lp-track span{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.78rem;
  letter-spacing:.1em;color:var(--lp-dim);white-space:nowrap}
.lp-track span::before{content:"\\002022";color:var(--lp-dimmer);margin-right:3rem}

/* the three layers ------------------------------------------------------- */
.lp-flow{display:grid;grid-template-columns:repeat(3,1fr);gap:0;
  border:1px solid var(--lp-rule);background:var(--lp-raised)}
.lp-flow > div{padding:1.9rem 1.7rem;border-right:1px solid var(--lp-rule)}
.lp-flow > div:last-child{border-right:0}
.lp-flow-n{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.18em;text-transform:uppercase;color:var(--lp-dimmer);
  display:block;margin-bottom:1rem}
.lp-flow h3{font-family:"Instrument Serif",Georgia,serif;font-style:italic;
  font-weight:400;font-size:1.45rem;margin:0 0 .6rem;color:var(--lp-ink)}
.lp-flow p{margin:0;color:var(--lp-dim);font-size:.92rem}
.lp-flow code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.76rem;
  color:var(--lp-signal)}
@media (max-width:800px){
  .lp-flow{grid-template-columns:1fr}
  .lp-flow > div{border-right:0;border-bottom:1px solid var(--lp-rule)}
  .lp-flow > div:last-child{border-bottom:0}
}

/* questions -------------------------------------------------------------- */
.lp-faq{border-top:1px solid var(--lp-rule)}
.lp-faq details{border-bottom:1px solid var(--lp-rule)}
.lp-faq summary{
  font-family:"Instrument Serif",Georgia,serif;font-size:1.3rem;
  padding:1.3rem 2.5rem 1.3rem 0;cursor:pointer;list-style:none;
  position:relative;color:var(--lp-ink);
}
.lp-faq summary::-webkit-details-marker{display:none}
.lp-faq summary::after{
  content:"+";position:absolute;right:.4rem;top:50%;transform:translateY(-50%);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:1.05rem;
  color:var(--lp-dimmer);
}
.lp-faq details[open] summary::after{content:"\\2212";color:var(--lp-signal)}
.lp-faq summary:hover{color:var(--lp-signal)}
.lp-faq summary:focus-visible{outline:1px solid var(--lp-signal);outline-offset:3px}
.lp-faq p{margin:0 0 1.4rem;color:var(--lp-dim);font-size:.96rem;max-width:62ch}

/* Motion: one orchestrated moment on load, and the measured mark sweeping to
   its reading on scroll. CSS only - no script, and it degrades to the static
   layout wherever scroll-driven timelines are unsupported. */
@media (prefers-reduced-motion:no-preference){
  .lp-rise{animation:lp-rise .8s cubic-bezier(.16,.84,.3,1) both}
  .lp-rise:nth-child(1){animation-delay:.05s}
  .lp-rise:nth-child(2){animation-delay:.14s}
  .lp-rise:nth-child(3){animation-delay:.23s}
  .lp-rise:nth-child(4){animation-delay:.32s}
  @keyframes lp-rise{
    from{opacity:0;transform:translateY(.7em)}
    to{opacity:1;transform:none}
  }
  .lp-scale .mark{
    animation:lp-sweep linear both;
    animation-timeline:view();
    animation-range:entry 15% cover 38%;
  }
  @keyframes lp-sweep{from{transform:translateX(-62%)}to{transform:none}}
  .lp-track{animation:lp-marquee 42s linear infinite}
  @keyframes lp-marquee{from{transform:none}to{transform:translateX(-50%)}}
}
"""


def _landing_shell(body: str, desc: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0A0D11">
<title>Orqen — measured behaviour for AI models</title>
<meta name="description" content="{e(desc)}">
{LANDING_FONTS}
<style>{LANDING_CSS}</style>
</head><body>{body}</body></html>"""


def _lp_scale(value: float, green: float, amber: float) -> str:
    """The same grammar as the passport's assay strip, in the instrument palette.
    Threshold zones are tonal steps of the ground; the only colour is the
    reading itself."""
    hi = max(amber * 1.6, value * 1.15, 0.05)
    W, top, h = 100.0, 3, 12

    def x(v):
        return max(0.0, min(W, v / hi * W))

    gx, ax, vx = x(green), x(amber), x(value)
    return f"""<svg class="lp-scale" viewBox="0 0 100 26" preserveAspectRatio="none"
 role="img" aria-label="measured {value:.3f}, against a pass limit of {green:g}">
<rect class="z1" x="0" y="{top}" width="{gx:.2f}" height="{h}"/>
<rect class="z2" x="{gx:.2f}" y="{top}" width="{max(0, ax - gx):.2f}" height="{h}"/>
<rect class="z3" x="{ax:.2f}" y="{top}" width="{max(0, W - ax):.2f}" height="{h}"/>
<line class="lim" x1="{gx:.2f}" y1="{top}" x2="{gx:.2f}" y2="{top + h}"/>
<line class="lim" x1="{ax:.2f}" y1="{top}" x2="{ax:.2f}" y2="{top + h}"/>
<line class="axis" x1="0" y1="{top + h}" x2="100" y2="{top + h}"/>
<line class="mark" x1="{vx:.2f}" y1="{top - 2.5}" x2="{vx:.2f}" y2="{top + h + 2.5}"/>
<text x="{gx + 1.2:.2f}" y="{top + h + 8}">pass limit {green:g}</text>
</svg>"""


PROBE_TABLE = [
    ("fairness", "Renders one prompt twice, differing only by name, gender or "
                 "geography, and measures how far the two answers diverge in "
                 "embedding space.", "6 pairs"),
    ("robustness", "Asks the same question three ways, and checks whether a "
                   "borderline refusal survives being rephrased.", "18 prompts"),
    ("calibration", "Has the model state a confidence per answer on a labelled "
                    "set, four items of which have no true answer, then bins "
                    "correctness against stated confidence.", "14 items"),
    ("leakage", "Prompts with the opening of a known public text and measures "
                "the longest verbatim run it reproduces.", "4 canaries"),
]


# The slot a marketing page fills with client logos. A hackathon project has no
# clients, and inventing them would contradict the one thing this project argues
# for. These are the documents the thresholds and taxonomies are referenced to,
# every one of which is cited on a passport.
STANDARDS_STRIP = [
    "CycloneDX 1.6",
    "OWASP AIBOM Generator",
    "NIST AI RMF MEASURE 2.5",
    "NIST AI RMF MEASURE 2.11",
    "OWASP LLM02",
    "OWASP LLM09",
    "EU AI Act Annex IV §2(g)",
    "AI Incident Database",
    "MITRE ATLAS",
    "Ed25519 attestation",
]

FAQ = [
    ("Does a green grade mean the model is safe?",
     "No, and the certificate says so on its face. Green means this suite of "
     "probes found nothing above threshold on the day it ran. Absence of a "
     "finding is not evidence of safety, and below 50% probe coverage the "
     "overall grade is <code>insufficient</code> rather than green - a broken "
     "audit must not be indistinguishable from a clean one."),
    ("Do you need the model weights?",
     "No. Every probe is black-box: prompts in, completions out. The audited "
     "model's identity is its Hugging Face id, but it can be served by any "
     "OpenAI-compatible gateway. That is deliberate, because it is the position "
     "nearly everyone deploying a model is actually in."),
    ("Where do the thresholds come from?",
     "Either a measured reference cohort or a published framework, and the "
     "passport records which. Percentile bands over a real cohort are "
     "measurement; asserted limits are judgement referenced to NIST AI RMF and "
     "the OWASP LLM Top 10. Where a cohort shows no usable spread the "
     "derivation refuses rather than inventing a band."),
    ("Can a passport be forged?",
     "It can be screenshotted and edited like any public page, which is why "
     "each one carries a detached Ed25519 signature over a canonical "
     "serialisation of its own content, verifiable against a key published at "
     "<code>/.well-known/orqen-signing-key.json</code>. That establishes "
     "provenance, not truth: it proves the document was issued by the key "
     "holder and not altered, and nothing about whether the measurements are "
     "correct."),
    ("Is a passport a conformity assessment?",
     "No. Orqen produces test evidence that can be filed against specific "
     "points in a technical file; it is not the technical file. Annex IV "
     "attaches to high-risk AI systems under Article 11, while a "
     "general-purpose model from a model hub is governed by Article 53 and "
     "Annex XI. Whether the audited model is a component of a high-risk system "
     "is the provider's determination, not Orqen's."),
    ("Who can see a passport once it is issued?",
     "Anyone with the link. There are no accounts and no authentication, "
     "because the artefact has to survive being pasted into an email, opened "
     "by someone with no login, and printed to PDF for a review pack. That is "
     "a scope decision, not an oversight."),
]


def landing_html(example: str = "meta-llama/Llama-3.1-8B-Instruct",
                 error: str = "") -> str:
    err = (f'<div class="lp-notice" role="alert"><b>Not accepted</b>{e(error)}</div>'
           if error else "")

    probe_rows = "".join(
        f"<tr><td>{e(n)}</td><td>{e(d)}</td><td>{e(c)}</td></tr>"
        for n, d, c in PROBE_TABLE)

    # Doubled so the marquee wraps at -50% with no visible seam.
    strip = "".join(f"<span>{e(s)}</span>" for s in STANDARDS_STRIP * 2)

    faq = "".join(
        f"<details><summary>{e(q)}</summary><p>{a}</p></details>"
        for q, a in FAQ)

    return _landing_shell(f"""
<nav class="lp-nav"><div class="lp-shell">
  <span class="lp-wordmark">Orqen</span>
  <ul>
    <li><a href="#gap">The gap</a></li>
    <li><a href="#layers">The layers</a></li>
    <li><a href="#method">The method</a></li>
    <li><a href="#plainly">The limits</a></li>
    <li><a href="#questions">Questions</a></li>
    <li><a href="/standards">Coverage</a></li>
    <li><a href="#top">Issue a passport &rarr;</a></li>
  </ul>
</div></nav>

<header class="lp-hero lp-shell" id="top">
  <p class="lp-eyebrow lp-rise">Empirical AI bill of materials</p>
  <h1 class="lp-stmt lp-rise">Every model ships with a description.
    <span class="lp-quiet">Almost none ship with</span> <em>a measurement.</em></h1>
  <p class="lp-body lp-rise">Orqen runs the model, records what it actually did,
    and issues a certificate you can send to anyone. <strong>No account, no
    install, permanent URL.</strong></p>
  {err}
  <form class="lp-form lp-rise" method="post" action="/audit">
    <label for="mid">Hugging Face model id</label>
    <input id="mid" name="model_id" required placeholder="org/model"
      spellcheck="false" autocomplete="off" autocapitalize="off">
    <button type="submit">Issue passport</button>
  </form>
  <p class="lp-try">Or run the example:
    <a href="/audit?model_id={e(example)}">{e(example)}</a> &middot; about 20 seconds</p>
</header>

<section class="lp-shell" aria-label="Standards referenced">
  <p class="lp-strip-label">Referenced against</p>
</section>
<div class="lp-strip"><div class="lp-track">{strip}</div></div>

<section class="lp-sec lp-shell" id="gap">
  <span class="lp-clause">The gap &mdash; measured 15 Aug 2026</span>
  <div class="lp-split">
    <div class="lp-split-row">
      <span class="lp-split-tag">Declared</span>
      <div>
        <p class="lp-declared">&ldquo;Llama 3.1 is intended for commercial and
          research use. Limitations and risks are documented in the model
          card.&rdquo;</p>
        <p class="lp-source">meta-llama/Llama-3.1-8B-Instruct &middot; model card
          &middot; unverified</p>
      </div>
    </div>
    <div class="lp-split-row">
      <span class="lp-split-tag">Measured</span>
      <div>
        <p class="lp-measured">Prompted with the opening lines of four well-known
          public texts, it reproduced <b>three of them verbatim</b>.</p>
        <p class="lp-figure">0.750</p>
        <p class="lp-source">leakage.verbatim_rate &middot; OWASP LLM02 sensitive
          information disclosure</p>
        {_lp_scale(0.750, 0.05, 0.15)}
      </div>
    </div>
  </div>
  <div class="lp-triad" style="margin-top:4.5rem">
    <div>
      <p class="lp-eyebrow">Stated plainly</p>
      <h2 class="lp-stmt">A model card is <em>a claim.</em></h2>
      <p class="lp-body">Existing bill-of-materials tooling reads the claim. It
        parses the card, the config, the licence chain, and scores how complete
        the paperwork is. None of it runs the model. A model can hold a
        perfectly complete card and still behave like the reading above.</p>
    </div>
    <div>
      <p class="lp-eyebrow">What Orqen adds</p>
      <h2 class="lp-stmt">Evidence, and <em>the receipts.</em></h2>
      <p class="lp-body">Four probe families, a fixed and versioned fingerprint,
        thresholds referenced to NIST AI RMF and the OWASP LLM Top 10, and every
        raw model response retained so the numbers can be disputed rather than
        trusted. The measurements are written back into a valid CycloneDX
        document.</p>
    </div>
  </div>
</section>

<section class="lp-sec lp-shell" id="layers">
  <span class="lp-clause">What a passport carries</span>
  <h2 class="lp-stmt" style="max-width:25ch;margin-bottom:2.6rem">Three layers.
    <span class="lp-quiet">One document,</span> <em>one signature.</em></h2>
  <div class="lp-flow">
    <div>
      <span class="lp-flow-n">01 &mdash; Declared</span>
      <h3>What the card claims.</h3>
      <p>The existing bill of materials, pulled through the OWASP AIBOM
        generator and falling back to the Hugging Face API. Every fallback is
        recorded in <code>_orqen.source</code> rather than being smoothed
        over.</p>
    </div>
    <div>
      <span class="lp-flow-n">02 &mdash; Measured</span>
      <h3>What the probes saw.</h3>
      <p>Four families, a fixed and versioned fingerprint, every raw response
        retained. The metrics are written back as CycloneDX properties, so the
        output is still a valid AIBOM &mdash; now carrying evidence.</p>
    </div>
    <div>
      <span class="lp-flow-n">03 &mdash; Correlated</span>
      <h3>How this profile failed before.</h3>
      <p>The fingerprint is rendered into the vocabulary incident reports
        actually use, then matched against the AI Incident Database and MITRE
        ATLAS by embedding similarity and taxonomy overlap.</p>
    </div>
  </div>
</section>

<section class="lp-sec lp-shell" id="method">
  <span class="lp-clause">The method</span>
  <h2 class="lp-stmt" style="max-width:26ch;margin-bottom:2.6rem">Black-box only.
    <span class="lp-quiet">No weights, no gradients,</span> <em>no privileged
    access.</em></h2>
  <table class="lp-probes">
    <thead><tr><th>Family</th><th>What it measures</th><th>Scale</th></tr></thead>
    <tbody>{probe_rows}</tbody>
  </table>
  <p class="lp-body" style="max-width:52ch">Anything Orqen can measure, you can
    measure about a model you did not train and cannot see inside &mdash; which
    is the position nearly everyone deploying a model is actually in.</p>
</section>

<section class="lp-sec lp-shell" id="plainly">
  <span class="lp-clause">The limits</span>
  <h2 class="lp-stmt" style="max-width:24ch;margin-bottom:2.8rem">What this
    <em>does not</em> tell you.</h2>
  <div class="lp-plainly">
    <div><h3>A pass is not a clearance</h3>
      <p>It means this suite found nothing. Absence of a finding is not evidence
        of safety, and the certificate says so on its face.</p></div>
    <div><h3>One moment, one gateway</h3>
      <p>Measurements describe the model as served on the issue date. The same
        weights served elsewhere may read differently.</p></div>
    <div><h3>Limits are referenced, not settled</h3>
      <p>Where no reference cohort has been measured, the thresholds express
        judgement against published frameworks. The passport names which.</p></div>
    <div><h3>Text models, for now</h3>
      <p>Text in, text out. No vision, no tabular, no continuous monitoring.
        The fingerprint schema is versioned to grow.</p></div>
  </div>
</section>

<section class="lp-sec lp-shell" id="questions">
  <span class="lp-clause">Asked before</span>
  <h2 class="lp-stmt" style="max-width:22ch;margin-bottom:2.6rem">The questions
    <em>worth asking</em> first.</h2>
  <div class="lp-faq">{faq}</div>
</section>

<footer class="lp-foot lp-shell">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span>CycloneDX 1.6 &middot; OWASP AIBOM &middot; NIST AI RMF &middot; AI Incident Database</span>
  <span><a href="#top">Issue a passport &rarr;</a></span>
</footer>
""", "Orqen runs an AI model, measures what it actually does, and issues a "
     "shareable certificate of measured behaviour.")



def _attestation_block(p: dict) -> str:
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


def standards_html() -> str:
    """The coverage matrix. Its job is to make Orqen's own citations checkable -
    including, and especially, the rows where the answer is 'nothing'."""
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
    unverified &middot; {counts[st.EXTERNAL]} not supplied, of
    {counts['total']}.</p>
  <table class="cov">
    <thead><tr><th>Ref</th><th>Requirement</th><th>Coverage</th>
      <th>What Orqen supplies</th></tr></thead>
    <tbody>{body}</tbody></table>
</section>""")

    return _shell("Orqen \u00b7 standards coverage", f"""<main class="sheet">
<header class="mast">
  <div class="mast-top"><span class="brand">Orqen</span>
    <span class="doctype">Standards coverage</span></div>
  <h1 class="specimen" style="font-size:1.5rem">What this tool supplies, and what it does not</h1>
  <p class="specimen-sub">{e(st.headline())}</p>
</header>
<section class="sec">
  <p class="lede" style="max-width:52rem">Orqen cites these frameworks on every
    passport it issues. A citation is a claim, and an unchecked claim is the
    thing this project exists to object to &mdash; so here is the claim, itemised.
    Rows marked <span class="lvl lvl-external">Not supplied</span> are the honest
    part of this page: they name work that has to come from somewhere else.
    Nothing here is legal advice, and section titles are paraphrased rather than
    quoted from the official texts.</p>
</section>
{''.join(blocks)}
<footer class="control">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span><a href="/">Issue a passport</a> &middot; <a href="/api/standards">this page as JSON</a></span>
</footer>
</main>""", "What Orqen supplies against Annex IV, NIST AI RMF and OWASP, and what it does not.")


def compare_html(a: dict, b: dict) -> str:
    """Two passports side by side.

    Ordered oldest-first so a delta reads as a change over time. Every metric is
    'higher is worse', so an increase is rendered as a regression regardless of
    which metric it is - that consistency is the reason the sign convention was
    fixed at the fingerprint layer."""
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
        'issued under different probe suites, so a difference may reflect a '
        'change in method rather than a change in the model. Only metrics '
        'present in both are shown.</div>')

    def head(p, label):
        d = _dt.datetime.utcfromtimestamp(p["created_at"]).strftime("%Y-%m-%d %H:%M UTC")
        sc = p.get("scores") or {}
        return (f"<div><dt>{label}</dt><dd>{e(p['model_id'])}<br>{e(d)}<br>"
                f"{e(p['slug'])} &middot; {e(sc.get('overall','?'))}</dd></div>")

    return _shell("Orqen \u00b7 comparison", f"""<main class="sheet">
<header class="mast">
  <div class="mast-top"><span class="brand">Orqen</span>
    <span class="doctype">Measurement comparison</span></div>
  <h1 class="specimen" style="font-size:1.5rem">Change in measured behaviour</h1>
</header>
<dl class="kv">{head(a, "Earlier")}{head(b, "Later")}</dl>
<section class="sec">
  <h2><span class="clause">&sect;1</span> Per-axis change</h2>
  {warn}
  <p class="lede">Every metric is oriented so that higher is worse, so an
    increase is a regression on any axis. Differences smaller than the spread
    reported on either passport are not evidence of change.</p>
  <table class="cmp">
    <thead><tr><th>Measurement</th><th>Earlier</th><th>Later</th><th>Change</th></tr></thead>
    <tbody>{''.join(rows) or '<tr><td colspan="4">No shared metrics.</td></tr>'}</tbody>
  </table>
</section>
<footer class="control">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span><a href="/p/{e(a['slug'])}">earlier passport</a> &middot;
        <a href="/p/{e(b['slug'])}">later passport</a></span>
</footer>
</main>""", "Change in measured behaviour between two Orqen passports.")


def error_html(code: int, message: str) -> str:
    return _shell(
        f"Orqen · {code}",
        f"""<main class="sheet"><section class="hero">
<span class="brand">Orqen</span>
<h1>{code}</h1>
<p class="claim">{e(message)}</p>
<form class="audit" method="post" action="/audit">
  <input name="model_id" required placeholder="org/model" spellcheck="false">
  <button type="submit">Issue passport</button>
</form>
</section></main>""")
