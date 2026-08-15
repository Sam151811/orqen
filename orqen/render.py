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
    'family=Inter+Tight:wght@400;500;600&'
    'family=IBM+Plex+Mono:wght@400;500&display=swap">'
)

LANDING_CSS = """
:root{
  --bg:#08090B;
  --panel:#0D0F13;
  --panel2:#111419;
  --line:#1A1D24;
  --line2:#252A33;
  --ink:#EDEFF2;
  --dim:#868D99;
  --dimmer:#4E5561;
  --signal:#F0A93B;
  --shell:78rem;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{
  margin:0;background:var(--bg);color:var(--ink);
  font-family:"Inter Tight",system-ui,sans-serif;font-size:16px;line-height:1.55;
  -webkit-font-smoothing:antialiased;overflow-x:hidden;
}
a{color:inherit}
.mono{font-family:"IBM Plex Mono",ui-monospace,monospace}
.shell{max-width:var(--shell);margin:0 auto;padding:0 1.5rem;width:100%}

/* type ------------------------------------------------------------------- */
h1,h2,h3{margin:0;font-weight:500;letter-spacing:-.03em;line-height:1.03}
.h-xl{font-size:clamp(2.6rem,7vw,5.4rem)}
.h-lg{font-size:clamp(2rem,4.6vw,3.4rem)}
.h-md{font-size:clamp(1.5rem,2.8vw,2.1rem)}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.66rem;
  letter-spacing:.22em;text-transform:uppercase;color:var(--dim);margin:0 0 1.2rem;
  display:flex;align-items:center;gap:.7rem;
}
.eyebrow::before{content:"";width:1.6rem;height:1px;background:var(--line2)}
.lede{color:var(--dim);font-size:1.05rem;max-width:48ch;margin:1.4rem 0 0}
.lede strong{color:var(--ink);font-weight:500}

/* nav -------------------------------------------------------------------- */
.nav{position:sticky;top:0;z-index:40;background:rgba(8,9,11,.78);
  backdrop-filter:blur(16px);border-bottom:1px solid var(--line)}
.nav .shell{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;
  height:3.6rem;gap:1rem}
.nav-l,.nav-r{display:flex;gap:1.6rem;align-items:center}
.nav-r{justify-content:flex-end}
.nav a{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;
  letter-spacing:.1em;color:var(--dim);text-decoration:none;
  display:inline-flex;align-items:center;gap:.45rem;
}
.nav a::after{content:"[ ]";color:var(--dimmer);transition:color .2s,transform .2s}
.nav a:hover{color:var(--ink)}
.nav a:hover::after{color:var(--signal);transform:translateX(2px)}
.mark{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.82rem;
  letter-spacing:.26em;text-transform:uppercase;color:var(--ink);
  text-decoration:none;white-space:nowrap;
}
.mark span{color:var(--signal)}
@media (max-width:880px){
  .nav .shell{grid-template-columns:auto 1fr}
  .nav-l{display:none}.nav-r{gap:1rem}
  .nav-r a:not(:last-child){display:none}
}

/* hero ------------------------------------------------------------------- */
.hero{position:relative;padding:7rem 0 5rem;overflow:hidden}
.hero-grid{
  position:absolute;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),
                   linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:74px 74px;
  mask-image:radial-gradient(ellipse 80% 60% at 50% 0%,#000 20%,transparent 75%);
  -webkit-mask-image:radial-gradient(ellipse 80% 60% at 50% 0%,#000 20%,transparent 75%);
  opacity:.6;
}
.hero .shell{position:relative;z-index:1}
.hero h1{max-width:16ch}
.hero h1 em{font-style:normal;color:var(--dimmer)}
.cta-row{display:flex;gap:.7rem;flex-wrap:wrap;margin:2.4rem 0 0}
.btn{
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.76rem;
  letter-spacing:.1em;text-transform:uppercase;padding:.9rem 1.5rem;
  border:1px solid var(--line2);color:var(--ink);text-decoration:none;
  display:inline-flex;align-items:center;gap:.6rem;cursor:pointer;
  background:transparent;transition:border-color .2s,color .2s,background .2s;
}
.btn:hover{border-color:var(--signal);color:var(--signal)}
.btn-fill{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.btn-fill:hover{background:var(--signal);border-color:var(--signal);color:var(--bg)}
.btn:focus-visible{outline:2px solid var(--signal);outline-offset:2px}

/* hero instrument panel (replaces the template's video) ------------------- */
.instrument{
  margin:3.4rem 0 0;border:1px solid var(--line);background:var(--panel);
  padding:1.4rem 1.5rem;position:relative;
}
.instrument-head{display:flex;justify-content:space-between;gap:1rem;
  flex-wrap:wrap;margin-bottom:1.1rem}
.instrument-head span{font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;color:var(--dimmer)}
.instrument-head b{color:var(--signal);font-weight:500}
.trace{width:100%;height:96px;display:block}
.trace .grid{stroke:var(--line);stroke-width:.5}
.trace .base{stroke:var(--line2);stroke-width:1}
.trace .sig{fill:none;stroke:var(--signal);stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round}
.trace .lim{stroke:var(--dimmer);stroke-width:1;stroke-dasharray:3 3}
.trace text{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:6px;
  fill:var(--dimmer)}

/* form ------------------------------------------------------------------- */
.form{display:flex;gap:.6rem;flex-wrap:wrap;max-width:40rem;margin:2rem 0 0}
.form label{flex:1 0 100%;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);margin-bottom:.6rem}
.form input{
  flex:1 1 18rem;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.92rem;padding:.9rem 1rem;color:var(--ink);background:var(--panel);
  border:1px solid var(--line2);border-radius:0;
}
.form input::placeholder{color:var(--dimmer)}
.form input:focus-visible{outline:none;border-color:var(--signal)}
.hint{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;
  color:var(--dim);margin:1rem 0 0}
.hint a{color:var(--ink);text-underline-offset:3px}
.hint a:hover{color:var(--signal)}
.notice{border-left:2px solid var(--signal);background:var(--panel);
  padding:.9rem 1.1rem;margin:1.8rem 0 0;max-width:40rem;font-size:.92rem}
.notice b{display:block;font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.62rem;letter-spacing:.16em;text-transform:uppercase;
  color:var(--signal);margin-bottom:.3rem}

/* ticker (the template's logo wall) --------------------------------------- */
.ticker{border-top:1px solid var(--line);border-bottom:1px solid var(--line);
  padding:1.5rem 0;overflow:hidden;position:relative}
.ticker::before,.ticker::after{content:"";position:absolute;top:0;bottom:0;
  width:6rem;z-index:2;pointer-events:none}
.ticker::before{left:0;background:linear-gradient(90deg,var(--bg),transparent)}
.ticker::after{right:0;background:linear-gradient(270deg,var(--bg),transparent)}
.ticker-label{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.64rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--dimmer);
  margin:0 0 1.3rem;text-align:center}
.track{display:flex;gap:3.2rem;width:max-content}
.track span{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.8rem;
  letter-spacing:.08em;color:var(--dim);white-space:nowrap;
  display:inline-flex;align-items:center;gap:3.2rem}
.track span::after{content:"/";color:var(--dimmer)}

/* sections --------------------------------------------------------------- */
.sec{padding:6rem 0;border-bottom:1px solid var(--line)}
.sec-head{max-width:46rem;margin:0 0 3.2rem}
.sec-head .lede{margin-top:1.2rem}

/* statement + split (the template's intersection block) ------------------- */
.split{border:1px solid var(--line);background:var(--panel)}
.split-row{padding:2rem 1.9rem;display:grid;grid-template-columns:8rem 1fr;
  gap:1.8rem;align-items:start}
.split-row + .split-row{border-top:1px solid var(--line)}
.split-tag{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.18em;text-transform:uppercase;color:var(--dimmer);padding-top:.4rem}
.declared{font-size:clamp(1.15rem,2.5vw,1.55rem);line-height:1.35;
  color:var(--dim);margin:0;letter-spacing:-.02em}
.measured{font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:clamp(1rem,2.2vw,1.3rem);line-height:1.4;margin:0;color:var(--ink)}
.measured b{color:var(--signal);font-weight:500}
.figure{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:2.8rem;
  color:var(--signal);line-height:1;margin:1.1rem 0 .2rem;
  font-variant-numeric:tabular-nums}
.src{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--dimmer);margin:.7rem 0 0}
.scale{width:100%;height:26px;display:block;margin:.6rem 0 0;overflow:visible}
.scale .z1{fill:#161C26}.scale .z2{fill:#121822}.scale .z3{fill:#0E141C}
.scale .axis{stroke:var(--line2);stroke-width:1}
.scale .lim{stroke:var(--dimmer);stroke-width:1;stroke-dasharray:2 2}
.scale .mark2{stroke:var(--signal);stroke-width:2.5}
.scale text{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:7.5px;
  fill:var(--dimmer)}
@media (max-width:700px){
  .split-row{grid-template-columns:1fr;gap:.9rem}
}

/* feature cards (the template's capabilities grid) ------------------------ */
.cards{display:grid;grid-template-columns:repeat(2,1fr);
  border:1px solid var(--line);background:var(--panel)}
.cards > article{padding:2.1rem 1.9rem;border-right:1px solid var(--line);
  border-bottom:1px solid var(--line);position:relative;transition:background .25s}
.cards > article:hover{background:var(--panel2)}
.cards > article:nth-child(2n){border-right:0}
.cards > article:nth-last-child(-n+2){border-bottom:0}
.card-n{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.18em;text-transform:uppercase;color:var(--dimmer);
  display:flex;justify-content:space-between;margin-bottom:1.4rem}
.card-n b{color:var(--signal);font-weight:400}
.cards h3{font-size:1.3rem;margin:0 0 .7rem}
.cards p{margin:0;color:var(--dim);font-size:.94rem}
@media (max-width:760px){
  .cards{grid-template-columns:1fr}
  .cards > article{border-right:0}
  .cards > article:last-child{border-bottom:0}
  .cards > article:nth-last-child(2){border-bottom:1px solid var(--line)}
}

/* pipeline (the template's integration ecosystem) ------------------------- */
.pipe{display:grid;grid-template-columns:repeat(3,1fr);gap:0;
  border:1px solid var(--line);background:var(--panel)}
.pipe > div{padding:2rem 1.8rem;border-right:1px solid var(--line);position:relative}
.pipe > div:last-child{border-right:0}
.pipe-n{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.18em;text-transform:uppercase;color:var(--dimmer);
  display:block;margin-bottom:1.1rem}
.pipe h3{font-size:1.35rem;margin:0 0 .6rem}
.pipe p{margin:0;color:var(--dim);font-size:.92rem}
.pipe code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.78rem;
  color:var(--signal)}
.pipe-arrow{position:absolute;right:-6px;top:2.35rem;width:11px;height:11px;
  background:var(--bg);border-right:1px solid var(--line2);
  border-top:1px solid var(--line2);transform:rotate(45deg);z-index:2}
@media (max-width:820px){
  .pipe{grid-template-columns:1fr}
  .pipe > div{border-right:0;border-bottom:1px solid var(--line)}
  .pipe > div:last-child{border-bottom:0}
  .pipe-arrow{display:none}
}

/* grade cards (the slot the template used for pricing tiers) -------------- */
.grades{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}
.grade{border:1px solid var(--line);background:var(--panel);padding:1.9rem 1.7rem;
  display:flex;flex-direction:column}
.grade.is-key{border-color:var(--line2)}
.grade-code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:3.2rem;
  line-height:1;color:var(--dimmer);margin:0 0 1.2rem;font-variant-numeric:tabular-nums}
.grade.is-key .grade-code{color:var(--signal)}
.grade h3{font-size:1.25rem;margin:0 0 .6rem}
.grade > p{margin:0 0 1.4rem;color:var(--dim);font-size:.92rem}
.grade ul{list-style:none;margin:auto 0 0;padding:1.2rem 0 0;
  border-top:1px solid var(--line)}
.grade li{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.72rem;
  color:var(--dim);padding:.42rem 0 .42rem 1.2rem;position:relative}
.grade li::before{content:"+";position:absolute;left:0;color:var(--dimmer)}
@media (max-width:820px){.grades{grid-template-columns:1fr}}

/* limits (replaces the template's testimonial carousel) ------------------- */
.limits{display:grid;grid-template-columns:repeat(auto-fit,minmax(15rem,1fr));
  gap:0;border:1px solid var(--line);background:var(--panel)}
.limits > div{padding:1.9rem 1.7rem;border-right:1px solid var(--line)}
.limits > div:last-child{border-right:0}
.limits h3{font-size:1.15rem;margin:0 0 .6rem}
.limits p{margin:0;color:var(--dim);font-size:.9rem}
@media (max-width:900px){
  .limits{grid-template-columns:1fr}
  .limits > div{border-right:0;border-bottom:1px solid var(--line)}
  .limits > div:last-child{border-bottom:0}
}

/* method table ----------------------------------------------------------- */
.probes{width:100%;border-collapse:collapse;
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.82rem}
.probes th{text-align:left;font-weight:400;color:var(--dimmer);font-size:.62rem;
  letter-spacing:.16em;text-transform:uppercase;padding:0 1rem .9rem 0;
  border-bottom:1px solid var(--line2)}
.probes td{padding:1.05rem 1rem 1.05rem 0;border-bottom:1px solid var(--line);
  vertical-align:top;color:var(--dim)}
.probes td:first-child{color:var(--ink);white-space:nowrap}
.probes td:last-child{color:var(--ink);text-align:right;white-space:nowrap;
  font-variant-numeric:tabular-nums}
@media (max-width:720px){.probes th:nth-child(2),.probes td:nth-child(2){display:none}}

/* faq -------------------------------------------------------------------- */
.faq{border-top:1px solid var(--line)}
.faq details{border-bottom:1px solid var(--line)}
.faq summary{font-size:1.2rem;padding:1.4rem 2.6rem 1.4rem 0;cursor:pointer;
  list-style:none;position:relative;color:var(--ink);letter-spacing:-.02em}
.faq summary::-webkit-details-marker{display:none}
.faq summary::after{content:"[ + ]";position:absolute;right:0;top:50%;
  transform:translateY(-50%);font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:.72rem;color:var(--dimmer)}
.faq details[open] summary::after{content:"[ - ]";color:var(--signal)}
.faq summary:hover{color:var(--signal)}
.faq summary:focus-visible{outline:1px solid var(--signal);outline-offset:3px}
.faq p{margin:0 0 1.5rem;color:var(--dim);font-size:.95rem;max-width:64ch}
.faq code{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.85em;
  color:var(--signal)}

/* closing cta ------------------------------------------------------------ */
.close{padding:6.5rem 0;text-align:center;position:relative;overflow:hidden}
.close-grid{position:absolute;inset:0;z-index:0;pointer-events:none;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),
                   linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:74px 74px;
  mask-image:radial-gradient(ellipse 70% 70% at 50% 50%,#000 10%,transparent 70%);
  -webkit-mask-image:radial-gradient(ellipse 70% 70% at 50% 50%,#000 10%,transparent 70%);
  opacity:.55}
.close .shell{position:relative;z-index:1}
.close .eyebrow{justify-content:center}
.close h2{max-width:18ch;margin:0 auto}
.close .lede{margin:1.4rem auto 0;text-align:center}
.close .form{margin:2.4rem auto 0;justify-content:center}
.close .form label{text-align:center}
.assur{display:flex;gap:2rem;justify-content:center;flex-wrap:wrap;margin:2.6rem 0 0}
.assur span{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.7rem;
  letter-spacing:.06em;color:var(--dim);display:inline-flex;align-items:center;gap:.5rem}
.assur span::before{content:"+";color:var(--signal)}

/* footer ----------------------------------------------------------------- */
.foot{border-top:1px solid var(--line);padding:3.4rem 0 2rem}
.foot-top{display:grid;grid-template-columns:2fr 1fr 1fr;gap:2.4rem}
.foot-brand p{color:var(--dim);font-size:.9rem;margin:1rem 0 0;max-width:34ch}
.foot h4{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.62rem;
  letter-spacing:.2em;text-transform:uppercase;color:var(--dimmer);
  margin:0 0 1.1rem;font-weight:400}
.foot ul{list-style:none;margin:0;padding:0}
.foot li{margin-bottom:.6rem}
.foot li a{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.74rem;
  color:var(--dim);text-decoration:none}
.foot li a:hover{color:var(--signal)}
.foot-bot{display:flex;justify-content:space-between;gap:1.5rem;flex-wrap:wrap;
  margin-top:3rem;padding-top:1.5rem;border-top:1px solid var(--line);
  font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.68rem;
  color:var(--dimmer)}
@media (max-width:760px){.foot-top{grid-template-columns:1fr 1fr}
  .foot-brand{grid-column:1 / -1}}

/* motion ----------------------------------------------------------------- */
@media (prefers-reduced-motion:no-preference){
  .rise{animation:rise .85s cubic-bezier(.16,.84,.3,1) both}
  .rise:nth-child(1){animation-delay:.04s}
  .rise:nth-child(2){animation-delay:.12s}
  .rise:nth-child(3){animation-delay:.2s}
  .rise:nth-child(4){animation-delay:.28s}
  .rise:nth-child(5){animation-delay:.36s}
  @keyframes rise{from{opacity:0;transform:translateY(.8em)}to{opacity:1;transform:none}}

  .track{animation:marquee 46s linear infinite}
  @keyframes marquee{from{transform:none}to{transform:translateX(-50%)}}

  .trace .sig{stroke-dasharray:1400;stroke-dashoffset:1400;
    animation:draw 2.6s cubic-bezier(.22,.7,.3,1) .35s both}
  @keyframes draw{to{stroke-dashoffset:0}}

  /* scroll-driven reveal, degrades to static where unsupported */
  .reveal{animation:reveal linear both;animation-timeline:view();
    animation-range:entry 8% cover 30%}
  @keyframes reveal{from{opacity:0;transform:translateY(1.4em)}to{opacity:1;transform:none}}

  .scale .mark2{animation:sweep linear both;animation-timeline:view();
    animation-range:entry 15% cover 38%}
  @keyframes sweep{from{transform:translateX(-62%)}to{transform:none}}
}
"""


def _landing_shell(body: str, desc: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#08090B">
<title>Orqen &mdash; an empirical AI bill of materials</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="Orqen">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
{LANDING_FONTS}
<style>{LANDING_CSS}</style>
</head><body>{body}</body></html>"""


def _lp_scale(value: float, green: float, amber: float) -> str:
    """The same grammar as the passport's assay strip. Threshold zones are tonal
    steps of the ground; the only colour is the reading itself."""
    hi = max(amber * 1.6, value * 1.15, 0.05)
    W, top, h = 100.0, 3, 12

    def x(v):
        return max(0.0, min(W, v / hi * W))

    gx, ax, vx = x(green), x(amber), x(value)
    return f"""<svg class="scale" viewBox="0 0 100 26" preserveAspectRatio="none"
 role="img" aria-label="measured {value:.3f}, against a pass limit of {green:g}">
<rect class="z1" x="0" y="{top}" width="{gx:.2f}" height="{h}"/>
<rect class="z2" x="{gx:.2f}" y="{top}" width="{max(0, ax - gx):.2f}" height="{h}"/>
<rect class="z3" x="{ax:.2f}" y="{top}" width="{max(0, W - ax):.2f}" height="{h}"/>
<line class="lim" x1="{gx:.2f}" y1="{top}" x2="{gx:.2f}" y2="{top + h}"/>
<line class="lim" x1="{ax:.2f}" y1="{top}" x2="{ax:.2f}" y2="{top + h}"/>
<line class="axis" x1="0" y1="{top + h}" x2="100" y2="{top + h}"/>
<line class="mark2" x1="{vx:.2f}" y1="{top - 2.5}" x2="{vx:.2f}" y2="{top + h + 2.5}"/>
<text x="{gx + 1.2:.2f}" y="{top + h + 8}">pass limit {green:g}</text>
</svg>"""


HERO_TRACE = """
<svg class="trace" viewBox="0 0 600 96" preserveAspectRatio="none" role="img"
 aria-label="Illustrative probe trace across a run">
  <g class="grid">
    <line x1="0" y1="24" x2="600" y2="24"/><line x1="0" y1="48" x2="600" y2="48"/>
    <line x1="0" y1="72" x2="600" y2="72"/>
    <line x1="120" y1="0" x2="120" y2="96"/><line x1="240" y1="0" x2="240" y2="96"/>
    <line x1="360" y1="0" x2="360" y2="96"/><line x1="480" y1="0" x2="480" y2="96"/>
  </g>
  <line class="lim" x1="0" y1="34" x2="600" y2="34"/>
  <text x="4" y="31">threshold</text>
  <path class="sig" d="M0,70 L40,68 L72,71 L104,58 L136,62 L168,44 L200,49
    L232,52 L264,30 L296,36 L328,33 L360,55 L392,51 L424,63 L456,59 L488,41
    L520,46 L552,66 L600,64"/>
  <line class="base" x1="0" y1="88" x2="600" y2="88"/>
</svg>
"""

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

# The structural slot the source template fills with client logos. This project
# has no clients, and inventing them would contradict the one thing it argues
# for, so the slot carries the documents the numbers are referenced to. Every
# entry appears on a real passport.
TICKER = [
    "CycloneDX 1.6", "OWASP AIBOM Generator", "NIST AI RMF MEASURE 2.5",
    "NIST AI RMF MEASURE 2.11", "OWASP LLM02", "OWASP LLM09",
    "EU AI Act Annex IV", "AI Incident Database", "MITRE ATLAS",
    "Ed25519 attestation",
]

CAPABILITIES = [
    ("Fairness", "Counterfactual pairs and embedding divergence",
     "One prompt, rendered twice, differing only by a name or a place. The "
     "reading is how far the two answers move apart, measured against a noise "
     "floor built from control pairs on the same model."),
    ("Robustness", "Paraphrase invariance and refusal stability",
     "The same question asked three ways. A safety boundary that holds under "
     "one phrasing and collapses under another is not a boundary, and this is "
     "the probe that says so."),
    ("Calibration", "Elicited-confidence ECE on a labelled set",
     "The only probe producing a quantity a model-risk function already "
     "recognises. Four items in the set have false premises, where the correct "
     "behaviour is to decline rather than answer confidently."),
    ("Leakage", "Memorisation canaries and longest verbatim run",
     "Prompted with the opening of a known public text, the probe measures the "
     "longest run the model reproduces word for word. Mapped to OWASP LLM02."),
]

GRADES = [
    ("0", "Passed the gate", False,
     "Every finding sat at or below its threshold on the day the audit ran.",
     ["Signed passport at a permanent URL",
      "CycloneDX document with measured properties",
      "Correlated incidents where the profile matches",
      "Safe to reference in a review pack"]),
    ("1", "Gate failure", True,
     "A finding exceeded threshold. In CI this fails the build.",
     ["Names the metric and the limit it cleared",
      "Records whether the limit was cohort-derived or asserted",
      "Retains every raw response behind the number",
      "orqen check --fail-on red"]),
    ("2", "Inconclusive", False,
     "Under 50% probe coverage, so no safety conclusion is available.",
     ["Grades insufficient, never green",
      "A broken audit must not resemble a clean one",
      "Names which probe families did not return",
      "Run deadline of 75 seconds enforced"]),
]

LIMITS = [
    ("A pass is not a clearance",
     "It means this suite found nothing above threshold. Absence of a finding "
     "is not evidence of safety, and the certificate says so on its face."),
    ("One moment, one gateway",
     "Measurements describe the model as served on the issue date. The same "
     "weights served elsewhere may read differently."),
    ("Limits are referenced, not settled",
     "Where no reference cohort has been measured, thresholds express judgement "
     "against published frameworks. The passport names which basis applied."),
    ("Text models, for now",
     "Text in, text out. No vision, no tabular, no continuous monitoring. The "
     "fingerprint schema is versioned to grow into it."),
]

FAQ = [
    ("Does a green grade mean the model is safe?",
     "No, and the certificate says so on its face. Green means this suite of "
     "probes found nothing above threshold on the day it ran. Below 50% probe "
     "coverage the overall grade is <code>insufficient</code> rather than "
     "green, because a broken audit must not be indistinguishable from a clean "
     "one."),
    ("Do you need the model weights?",
     "No. Every probe is black-box: prompts in, completions out. The audited "
     "model's identity is its Hugging Face id, but it can be served through any "
     "OpenAI-compatible gateway. That is deliberate, because it is the position "
     "nearly everyone deploying a model is actually in."),
    ("Where do the thresholds come from?",
     "Either a measured reference cohort or a published framework, and the "
     "passport records which. Percentile bands over a real cohort are "
     "measurement; asserted limits are judgement referenced to NIST AI RMF and "
     "the OWASP LLM Top 10. Where a cohort shows no usable spread, the "
     "derivation refuses rather than inventing a band."),
    ("Can a passport be forged?",
     "It can be screenshotted and edited like any public page, which is why "
     "each one carries a detached Ed25519 signature over a canonical "
     "serialisation of its own content, verifiable against a key published at "
     "<code>/.well-known/orqen-signing-key.json</code>. That establishes "
     "provenance, not truth: it proves the document was issued by the key "
     "holder and not altered since, and nothing about whether the measurements "
     "are correct."),
    ("Is a passport a conformity assessment?",
     "No. Orqen produces test evidence that can be filed against specific "
     "points in a technical file; it is not the technical file. Annex IV "
     "attaches to high-risk AI systems under Article 11, while a "
     "general-purpose model from a model hub is governed by Article 53 and "
     "Annex XI. Whether the audited model is a component of a high-risk system "
     "is the provider's determination, not Orqen's."),
    ("Who can see a passport once it is issued?",
     "Anyone with the link. There are no accounts and no authentication, "
     "because the artefact has to survive being pasted into an email, opened by "
     "someone with no login, and printed to PDF for a review pack. That is a "
     "scope decision, not an oversight."),
]


def landing_html(example: str = "meta-llama/Llama-3.1-8B-Instruct",
                 error: str = "") -> str:
    err = (f'<div class="notice" role="alert"><b>Not accepted</b>{e(error)}</div>'
           if error else "")

    probe_rows = "".join(
        f"<tr><td>{e(n)}</td><td>{e(d)}</td><td>{e(c)}</td></tr>"
        for n, d, c in PROBE_TABLE)

    # Doubled so the marquee wraps at -50% with no visible seam.
    ticker = "".join(f"<span>{e(t)}</span>" for t in TICKER * 2)

    caps = "".join(
        f'<article class="reveal"><div class="card-n"><span>{e(k)}</span>'
        f'<b>0{i}</b></div><h3>{e(t)}</h3><p>{e(d)}</p></article>'
        for i, (t, k, d) in enumerate(CAPABILITIES, 1))

    grades = "".join(
        f'<div class="grade reveal{" is-key" if key else ""}">'
        f'<p class="grade-code">{e(code)}</p><h3>{e(title)}</h3><p>{e(desc)}</p>'
        f'<ul>{"".join(f"<li>{e(b)}</li>" for b in bullets)}</ul></div>'
        for code, title, key, desc, bullets in GRADES)

    limits = "".join(
        f'<div><h3>{e(t)}</h3><p>{e(d)}</p></div>' for t, d in LIMITS)

    faq = "".join(
        f"<details><summary>{e(q)}</summary><p>{a}</p></details>"
        for q, a in FAQ)

    return _landing_shell(f"""
<nav class="nav"><div class="shell">
  <div class="nav-l">
    <a href="#method">Method</a>
    <a href="#pipeline">Pipeline</a>
  </div>
  <a class="mark" href="#top">Orqen<span>.</span></a>
  <div class="nav-r">
    <a href="#questions">Questions</a>
    <a href="/standards">Coverage</a>
  </div>
</div></nav>

<header class="hero" id="top">
  <div class="hero-grid"></div>
  <div class="shell">
    <p class="eyebrow rise">Empirical AI bill of materials</p>
    <h1 class="h-xl rise">Every model ships with a description.
      <em>Almost none ship with a measurement.</em></h1>
    <p class="lede rise">Orqen runs the model, records what it actually did, and
      issues a certificate you can send to anyone.
      <strong>No account, no install, permanent URL.</strong></p>
    <div class="cta-row rise">
      <a class="btn" href="#pipeline">How it works</a>
      <a class="btn" href="/standards">Standards coverage</a>
    </div>
    {err}
    <form class="form rise" method="post" action="/audit">
      <label for="mid">Hugging Face model id</label>
      <input id="mid" name="model_id" required placeholder="org/model"
        spellcheck="false" autocomplete="off" autocapitalize="off">
      <button class="btn btn-fill" type="submit">Issue passport</button>
    </form>
    <p class="hint">Or run the example:
      <a href="/audit?model_id={e(example)}">{e(example)}</a> &middot; about 20 seconds</p>
    <div class="instrument rise">
      <div class="instrument-head">
        <span>Probe trace &middot; illustrative</span>
        <span>Excursions above threshold become findings &middot; <b>4 families</b></span>
      </div>
      {HERO_TRACE}
    </div>
  </div>
</header>

<section aria-label="Standards referenced">
  <div class="shell"><p class="ticker-label">Referenced against</p></div>
  <div class="ticker"><div class="track">{ticker}</div></div>
</section>

<section class="sec" id="gap">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">The gap</p>
      <h2 class="h-lg">The declared and the measured are not the same document.</h2>
      <p class="lede">Existing bill-of-materials tooling reads the claim: the
        card, the config, the licence chain. None of it runs the model. A model
        can hold a complete card and still return the reading below.</p>
    </div>
    <div class="split reveal">
      <div class="split-row">
        <span class="split-tag">Declared</span>
        <div>
          <p class="declared">&ldquo;Llama 3.1 is intended for commercial and
            research use. Limitations and risks are documented in the model
            card.&rdquo;</p>
          <p class="src">meta-llama/Llama-3.1-8B-Instruct &middot; model card &middot; unverified</p>
        </div>
      </div>
      <div class="split-row">
        <span class="split-tag">Measured</span>
        <div>
          <p class="measured">Prompted with the opening lines of four well-known
            public texts, it reproduced <b>three of them verbatim</b>.</p>
          <p class="figure">0.750</p>
          <p class="src">leakage.verbatim_rate &middot; OWASP LLM02 sensitive information disclosure</p>
          {_lp_scale(0.750, 0.05, 0.15)}
        </div>
      </div>
    </div>
  </div>
</section>

<section class="sec" id="capabilities">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">Probe families</p>
      <h2 class="h-lg">Four measurements, one fingerprint.</h2>
      <p class="lede">Each family returns a fixed set of metrics in a versioned
        order, so two runs of the same model are comparable and a drift between
        them is a fact rather than an impression.</p>
    </div>
    <div class="cards">{caps}</div>
  </div>
</section>

<section class="sec" id="pipeline">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">The pipeline</p>
      <h2 class="h-lg">Three layers. One document, one signature.</h2>
    </div>
    <div class="pipe reveal">
      <div>
        <span class="pipe-n">01 &mdash; Declared</span>
        <h3>What the card claims.</h3>
        <p>The existing bill of materials, pulled through the OWASP AIBOM
          generator, falling back to the Hugging Face API and then to a minimal
          stub. Every fallback is recorded in <code>_orqen.source</code> rather
          than smoothed over.</p>
        <div class="pipe-arrow"></div>
      </div>
      <div>
        <span class="pipe-n">02 &mdash; Measured</span>
        <h3>What the probes saw.</h3>
        <p>Four families, a fixed and versioned fingerprint, every raw response
          retained. The metrics are written back as CycloneDX properties, so the
          output is still a valid AIBOM &mdash; now carrying evidence.</p>
        <div class="pipe-arrow"></div>
      </div>
      <div>
        <span class="pipe-n">03 &mdash; Correlated</span>
        <h3>How this profile failed before.</h3>
        <p>The fingerprint is rendered into the vocabulary incident reports
          actually use, then matched against the AI Incident Database and MITRE
          ATLAS by embedding similarity and taxonomy overlap.</p>
      </div>
    </div>
  </div>
</section>

<section class="sec" id="method">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">The method</p>
      <h2 class="h-lg">Black-box only. No weights, no gradients, no privileged access.</h2>
      <p class="lede">Anything Orqen can measure, you can measure about a model
        you did not train and cannot see inside &mdash; which is the position
        nearly everyone deploying a model is actually in.</p>
    </div>
    <table class="probes reveal">
      <thead><tr><th>Family</th><th>What it measures</th><th>Scale</th></tr></thead>
      <tbody>{probe_rows}</tbody>
    </table>
  </div>
</section>

<section class="sec" id="outcomes">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">Exit codes</p>
      <h2 class="h-lg">What an audit returns.</h2>
      <p class="lede">The same three outcomes on the command line, in CI, and on
        the passport. The third exists because a broken audit must not be
        indistinguishable from a clean one.</p>
    </div>
    <div class="grades">{grades}</div>
  </div>
</section>

<section class="sec" id="limits">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">Stated plainly</p>
      <h2 class="h-lg">What this does not tell you.</h2>
    </div>
    <div class="limits reveal">{limits}</div>
  </div>
</section>

<section class="sec" id="questions">
  <div class="shell">
    <div class="sec-head reveal">
      <p class="eyebrow">Asked before</p>
      <h2 class="h-lg">The questions worth asking first.</h2>
    </div>
    <div class="faq reveal">{faq}</div>
  </div>
</section>

<section class="close">
  <div class="close-grid"></div>
  <div class="shell">
    <p class="eyebrow">Issue a passport</p>
    <h2 class="h-lg">Measure a model in about twenty seconds.</h2>
    <p class="lede">Paste a Hugging Face id. Orqen runs the suite, writes the
      measurements into a CycloneDX document, signs it, and gives you a URL.</p>
    <form class="form" method="post" action="/audit">
      <label for="mid2">Hugging Face model id</label>
      <input id="mid2" name="model_id" required placeholder="org/model"
        spellcheck="false" autocomplete="off" autocapitalize="off">
      <button class="btn btn-fill" type="submit">Issue passport</button>
    </form>
    <div class="assur">
      <span>No account required</span>
      <span>Permanent public URL</span>
      <span>Signed and independently verifiable</span>
    </div>
  </div>
</section>

<footer class="foot"><div class="shell">
  <div class="foot-top">
    <div class="foot-brand">
      <a class="mark" href="#top">Orqen<span>.</span></a>
      <p>An empirical AI bill of materials. Runs the model, measures what it
        does, and writes the result back into the standard document.</p>
    </div>
    <div>
      <h4>Sections</h4>
      <ul>
        <li><a href="#gap">The gap</a></li>
        <li><a href="#capabilities">Probe families</a></li>
        <li><a href="#pipeline">The pipeline</a></li>
        <li><a href="#method">The method</a></li>
        <li><a href="#questions">Questions</a></li>
      </ul>
    </div>
    <div>
      <h4>Reference</h4>
      <ul>
        <li><a href="/standards">Standards coverage</a></li>
        <li><a href="/.well-known/orqen-signing-key.json">Signing key</a></li>
        <li><a href="/health">Service status</a></li>
        <li><a href="#limits">Scope limits</a></li>
      </ul>
    </div>
  </div>
  <div class="foot-bot">
    <span>Orqen &middot; empirical AI bill of materials</span>
    <span>CycloneDX 1.6 &middot; OWASP AIBOM &middot; NIST AI RMF &middot; MITRE ATLAS</span>
  </div>
</div></footer>
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
