"""The application surface.

Two visual registers, on purpose, and the split is the argument:

  this module   the instrument you operate - pure monochrome, IBM Plex Mono
                across its weight range, a point field behind everything
  render.py     the document it issues - pale certificate stock, three-family
                typography, prints to PDF, no script at all

A passport has to survive being forwarded to someone with no account and
attached to a review pack. An operating surface has to feel like instrumentation.
Making them look the same would compromise one of those jobs.

Design tokens, chrome and the scene are lifted from the dashboard design
unchanged. What is new is that every number on the fleet view comes from stored
passports rather than a generator.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import statistics

FAVICON = """<svg width="144" height="144" viewBox="0 0 144 144" fill="none" \
xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Orqen">
  <rect width="144" height="144" fill="white"/>
  <g stroke="black" stroke-width="14" fill="none">
    <circle cx="66" cy="62" r="34"/>
    <path d="M96 62 V116" stroke-linecap="butt"/>
  </g>
  <rect x="18" y="122" width="108" height="8" fill="black"/>
  <style>
    @media (prefers-color-scheme: dark) {
      rect[width="144"] { fill: #000; }
      g { stroke: #fff; }
      rect[y="122"] { fill: #fff; }
    }
  </style>
</svg>"""

MANIFEST = {
    "name": "Orqen",
    "short_name": "Orqen",
    "description": "Measured behaviour for AI models. Runs the model, records "
                   "what it did, issues a certificate.",
    "start_url": "/",
    "display": "standalone",
    "background_color": "#000000",
    "theme_color": "#000000",
    "icons": [{"src": "/favicon.svg", "sizes": "any",
               "type": "image/svg+xml", "purpose": "any"}],
}

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=IBM+Plex+Mono:wght@100;200;300;400;500;600&'
    'family=IBM+Plex+Sans:wght@300;400;500&display=swap">'
)

CSS = """
:root{
  --black:#000; --white:#fff;
  --panel:rgba(0,0,0,.58);
  --rule:rgba(255,255,255,.14);
  --rule-strong:rgba(255,255,255,.28);
  --dim:rgba(255,255,255,.46);
  --mid:rgba(255,255,255,.68);

  --font-display:"IBM Plex Mono", ui-monospace, monospace;
  --font-body:"IBM Plex Mono", ui-monospace, monospace;
  /* Prose only. Long paragraphs set in mono are hard work, and the certificate
     has several; Plex Sans is a sibling of Plex Mono so the system stays tight. */
  --font-prose:"IBM Plex Sans", system-ui, sans-serif;

  --text-xs:.75rem; --text-sm:.875rem; --text-base:1rem; --text-lg:1.125rem;
  --text-xl:1.25rem; --text-2xl:1.5rem; --text-3xl:1.875rem;
  --text-5xl:3rem; --text-7xl:4.5rem; --text-9xl:8rem;

  --sp:.25rem; --radius:.25rem; --shell:1440px;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--black);color:var(--white);font-family:var(--font-body);
  font-size:var(--text-base);font-weight:300;line-height:1.5;
  -webkit-font-smoothing:antialiased;overflow-x:hidden}
a{color:inherit}
canvas{display:block}

#scene{position:fixed;inset:0;z-index:0;pointer-events:none}
#scene-veil{position:fixed;inset:0;z-index:1;pointer-events:none;
  background:
    radial-gradient(ellipse 130% 95% at 50% 8%, rgba(0,0,0,0), rgba(0,0,0,.42) 78%),
    linear-gradient(180deg, rgba(0,0,0,0) 0%, rgba(0,0,0,.30) 62%, rgba(0,0,0,.58) 100%)}
.shell{position:relative;z-index:2;max-width:var(--shell);margin:0 auto;
  padding:0 calc(var(--sp)*6)}

/* chrome ------------------------------------------------------------------ */
.bar{position:sticky;top:0;z-index:20;border-bottom:1px solid var(--rule);
  background:rgba(0,0,0,.62);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px)}
.bar-in{max-width:var(--shell);margin:0 auto;padding:0 calc(var(--sp)*6);
  height:calc(var(--sp)*14);display:flex;align-items:center;justify-content:space-between;
  gap:calc(var(--sp)*6)}
.mark{font-size:var(--text-sm);font-weight:500;letter-spacing:.22em;text-transform:uppercase;
  text-decoration:none;white-space:nowrap}
.mark em{font-style:normal;color:var(--dim)}
.nav{display:flex;gap:calc(var(--sp)*6);list-style:none;margin:0;padding:0;
  font-size:var(--text-xs);letter-spacing:.16em;text-transform:uppercase}
.nav a{color:var(--dim);text-decoration:none;transition:color .18s}
.nav a:hover,.nav a:focus-visible,.nav a[aria-current="page"]{color:var(--white)}
@media (max-width:820px){.nav li:not(:last-child){display:none}}
.status{display:flex;align-items:center;gap:calc(var(--sp)*2);font-size:var(--text-xs);
  letter-spacing:.14em;text-transform:uppercase;color:var(--dim);margin:0}
.dot{width:6px;height:6px;border-radius:50%;background:var(--white)}

.ranges{display:flex;gap:1px;border:1px solid var(--rule);border-radius:var(--radius);
  overflow:hidden}
.ranges button{font-family:var(--font-body);font-size:var(--text-xs);font-weight:400;
  letter-spacing:.14em;text-transform:uppercase;padding:calc(var(--sp)*2) calc(var(--sp)*4);
  background:transparent;color:var(--dim);border:0;cursor:pointer;
  transition:background .18s,color .18s}
.ranges button:hover{color:var(--white)}
.ranges button[aria-pressed="true"]{background:var(--white);color:var(--black)}
.ranges button:focus-visible{outline:2px solid var(--white);outline-offset:-2px}

/* masthead ---------------------------------------------------------------- */
.head{padding:calc(var(--sp)*28) 0 calc(var(--sp)*20)}
.eyebrow{font-size:var(--text-xs);letter-spacing:.28em;text-transform:uppercase;
  color:var(--dim);margin:0 0 calc(var(--sp)*8);display:flex;align-items:center;
  gap:calc(var(--sp)*3)}
.eyebrow::before{content:"";width:calc(var(--sp)*8);height:1px;background:var(--rule-strong)}
.head h1{font-family:var(--font-display);font-size:clamp(2.5rem,7vw,var(--text-7xl));
  font-weight:200;line-height:1.02;letter-spacing:-.04em;margin:0;max-width:22ch}
.head h1 b{font-weight:500}
.head p{color:var(--mid);font-size:var(--text-lg);max-width:58ch;
  margin:calc(var(--sp)*8) 0 0;font-weight:300}
.head p strong{color:var(--white);font-weight:400}

.readout{display:flex;flex-wrap:wrap;gap:calc(var(--sp)*12);margin:calc(var(--sp)*14) 0 0}
.readout div{min-width:9rem}
.readout dt{font-size:var(--text-xs);letter-spacing:.18em;text-transform:uppercase;
  color:var(--dim);margin:0 0 calc(var(--sp)*2)}
.readout dd{margin:0;font-size:var(--text-3xl);font-weight:200;letter-spacing:-.03em;
  font-variant-numeric:tabular-nums}

/* audit form -------------------------------------------------------------- */
.audit{display:flex;gap:calc(var(--sp)*2);flex-wrap:wrap;max-width:40rem;
  margin:calc(var(--sp)*12) 0 0}
.audit label{flex:1 0 100%;font-size:var(--text-xs);letter-spacing:.18em;
  text-transform:uppercase;color:var(--dim);margin-bottom:calc(var(--sp)*3)}
.audit input{flex:1 1 18rem;font-family:var(--font-body);font-size:var(--text-sm);
  font-weight:300;padding:calc(var(--sp)*4) calc(var(--sp)*4);
  background:var(--panel);color:var(--white);border:1px solid var(--rule);
  border-radius:var(--radius);backdrop-filter:blur(12px)}
.audit input::placeholder{color:var(--dim)}
.audit input:focus-visible{outline:none;border-color:var(--white)}
.audit button{font-family:var(--font-body);font-size:var(--text-xs);font-weight:500;
  letter-spacing:.16em;text-transform:uppercase;
  padding:calc(var(--sp)*4) calc(var(--sp)*7);cursor:pointer;
  background:var(--white);color:var(--black);border:1px solid var(--white);
  border-radius:var(--radius);transition:background .18s,color .18s}
.audit button:hover{background:transparent;color:var(--white)}
.audit button:focus-visible{outline:2px solid var(--white);outline-offset:2px}
.hint{font-size:var(--text-xs);letter-spacing:.06em;color:var(--dim);
  margin:calc(var(--sp)*4) 0 0}
.hint a{color:var(--white)}

/* sections + tiles -------------------------------------------------------- */
.section{padding:calc(var(--sp)*16) 0;border-top:1px solid var(--rule)}
.section-head{display:flex;align-items:baseline;justify-content:space-between;
  gap:calc(var(--sp)*6);margin:0 0 calc(var(--sp)*10);flex-wrap:wrap}
.section-head h2{font-family:var(--font-display);font-size:var(--text-2xl);
  font-weight:200;letter-spacing:-.02em;margin:0}
.section-head span{font-size:var(--text-xs);letter-spacing:.18em;text-transform:uppercase;
  color:var(--dim)}
.lede{color:var(--mid);max-width:64ch;font-size:var(--text-sm);
  margin:calc(var(--sp)*-4) 0 calc(var(--sp)*10)}

.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:calc(var(--sp)*3)}
.tile{position:relative;padding:calc(var(--sp)*6);border:1px solid var(--rule);
  border-radius:var(--radius);background:var(--panel);backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);transition:border-color .22s,background .22s,transform .22s}
.tile:hover{border-color:var(--rule-strong);background:rgba(0,0,0,.72);transform:translateY(-2px)}
.tile:focus-within{border-color:var(--white)}
.tile-label{font-size:var(--text-xs);letter-spacing:.16em;text-transform:uppercase;
  color:var(--dim);margin:0 0 calc(var(--sp)*4);display:flex;justify-content:space-between;
  gap:calc(var(--sp)*2)}
.tile-value{font-size:var(--text-5xl);font-weight:200;line-height:1;letter-spacing:-.04em;
  margin:0;font-variant-numeric:tabular-nums}
.tile-unit{font-size:var(--text-lg);color:var(--dim);margin-left:calc(var(--sp)*1)}
.tile-delta{font-size:var(--text-xs);letter-spacing:.06em;color:var(--mid);
  margin:calc(var(--sp)*3) 0 0}
.tile-delta[data-dir="down"]{color:var(--dim)}
.spark{width:100%;height:44px;display:block;margin:calc(var(--sp)*4) 0 0}
.spark path{fill:none;stroke:var(--white);stroke-width:1.25;stroke-linejoin:round;
  stroke-linecap:round}
.spark .fill{fill:rgba(255,255,255,.07);stroke:none}
.spark .base{stroke:var(--rule);stroke-width:1}
.spark .lim{stroke:var(--dim);stroke-width:1;stroke-dasharray:2 3}

/* table ------------------------------------------------------------------- */
.table-wrap{border:1px solid var(--rule);border-radius:var(--radius);background:var(--panel);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:var(--text-sm);min-width:52rem}
th{text-align:left;font-weight:400;font-size:var(--text-xs);letter-spacing:.16em;
  text-transform:uppercase;color:var(--dim);padding:calc(var(--sp)*5) calc(var(--sp)*6);
  border-bottom:1px solid var(--rule);white-space:nowrap;cursor:pointer;user-select:none;
  background:transparent}
th:hover{color:var(--white)}
th:focus-visible{outline:2px solid var(--white);outline-offset:-2px}
th[aria-sort]::after{content:"";margin-left:calc(var(--sp)*2);color:var(--white)}
th[aria-sort="ascending"]::after{content:"\\2191"}
th[aria-sort="descending"]::after{content:"\\2193"}
td{padding:calc(var(--sp)*4) calc(var(--sp)*6);border-bottom:1px solid rgba(255,255,255,.07);
  color:var(--mid);font-weight:300;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background .16s}
tbody tr:hover{background:rgba(255,255,255,.045)}
td.num{text-align:right;font-variant-numeric:tabular-nums;color:var(--white)}
td.name{color:var(--white)}
td.name a{text-decoration:none;border-bottom:1px solid var(--rule-strong)}
td.name a:hover{border-bottom-color:var(--white)}

/* A determination is never colour alone: the word carries it, and the dot is
   reinforcement. This surface is monochrome, so the grade has to read as text. */
.grade{display:inline-flex;align-items:center;gap:calc(var(--sp)*2);
  font-size:var(--text-xs);letter-spacing:.12em;text-transform:uppercase;
  white-space:nowrap}
.grade::before{content:"";width:5px;height:5px;border-radius:50%;background:currentColor}
.grade[data-g="red"]{color:var(--white);font-weight:500}
.grade[data-g="amber"]{color:var(--mid)}
.grade[data-g="indeterminate"]{color:var(--mid)}
.grade[data-g="green"]{color:var(--dim)}
.grade[data-g="insufficient"]{color:var(--dim);font-style:italic}

.filter{display:flex;gap:calc(var(--sp)*3);align-items:center;
  margin:0 0 calc(var(--sp)*6);flex-wrap:wrap}
.filter input{font-family:var(--font-body);font-size:var(--text-sm);font-weight:300;
  padding:calc(var(--sp)*3) calc(var(--sp)*4);min-width:16rem;background:var(--panel);
  color:var(--white);border:1px solid var(--rule);border-radius:var(--radius)}
.filter input::placeholder{color:var(--dim)}
.filter input:focus-visible{outline:none;border-color:var(--white)}
.filter .count{font-size:var(--text-xs);letter-spacing:.14em;text-transform:uppercase;
  color:var(--dim)}
.empty{padding:calc(var(--sp)*12) calc(var(--sp)*6);text-align:center;color:var(--dim);
  font-size:var(--text-sm)}
.empty strong{color:var(--white);font-weight:400;display:block;
  margin-bottom:calc(var(--sp)*2)}

.notice{border:1px solid var(--rule-strong);border-left-width:2px;
  padding:calc(var(--sp)*4) calc(var(--sp)*5);margin:calc(var(--sp)*8) 0 0;
  max-width:46rem;font-size:var(--text-sm);color:var(--mid);background:var(--panel)}
.notice b{display:block;font-size:var(--text-xs);letter-spacing:.16em;
  text-transform:uppercase;color:var(--white);margin-bottom:calc(var(--sp)*2)}

.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
  overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;border:0}

.foot{border-top:1px solid var(--rule);padding:calc(var(--sp)*10) 0 calc(var(--sp)*16);
  display:flex;justify-content:space-between;gap:calc(var(--sp)*6);flex-wrap:wrap;
  font-size:var(--text-xs);letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.foot a{color:var(--mid);text-decoration:none}
.foot a:hover{color:var(--white)}

.cue{position:fixed;left:50%;bottom:calc(var(--sp)*6);transform:translateX(-50%);
  z-index:15;font-size:var(--text-xs);letter-spacing:.24em;text-transform:uppercase;
  color:var(--dim);display:flex;flex-direction:column;align-items:center;
  gap:calc(var(--sp)*2);transition:opacity .4s;pointer-events:none}
.cue i{display:block;width:1px;height:calc(var(--sp)*8);
  background:linear-gradient(var(--rule-strong),transparent)}

@media (max-width:1100px){.tiles{grid-template-columns:repeat(2,1fr)}}
@media (max-width:680px){
  .tiles{grid-template-columns:1fr}
  .head{padding:calc(var(--sp)*16) 0 calc(var(--sp)*12)}
  .bar-in{height:calc(var(--sp)*12)}
  .readout{gap:calc(var(--sp)*8)}
}

@media (prefers-reduced-motion:no-preference){
  .reveal{opacity:0;transform:translateY(18px);
    transition:opacity .7s cubic-bezier(.16,.84,.3,1), transform .7s cubic-bezier(.16,.84,.3,1)}
  .reveal.in{opacity:1;transform:none}
  .dot{animation:pulse 2.4s ease-in-out infinite}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
}
@media (prefers-reduced-motion:reduce){
  .reveal{opacity:1;transform:none}
  html{scroll-behavior:auto}
}
"""

SCENE_JS = """
/* Three.js from any of three CDNs. A blocked source costs the background and
   nothing else, so the interface boots first and the scene attaches after. */
(function () {
  var SOURCES = [
    "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
    "https://unpkg.com/three@0.128.0/build/three.min.js",
    "https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"
  ];
  window.__threeReady = new Promise(function (resolve) {
    var i = 0;
    (function next() {
      if (i >= SOURCES.length) { return resolve(false); }
      var s = document.createElement("script");
      s.src = SOURCES[i++];
      s.onload = function () { resolve(true); };
      s.onerror = next;
      document.head.appendChild(s);
    })();
  });
})();
"""

APP_JS = """
(function () {
  "use strict";
  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---- scene: monochrome point field, wireframe core, slow drift ---- */
  function initScene() {
    var canvas = document.getElementById("scene");
    if (!canvas) return;
    if (!window.THREE) { canvas.style.display = "none"; return; }
    var renderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
    } catch (err) { canvas.style.display = "none"; return; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    var scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.032);
    var camera = new THREE.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.1, 200);
    camera.position.set(0, 0, 26);
    var group = new THREE.Group(); scene.add(group);

    var COUNT = 5200, pos = new Float32Array(COUNT * 3);
    for (var i = 0; i < COUNT; i++) {
      var u = Math.random(), v = Math.random();
      var theta = 2 * Math.PI * u, phi = Math.acos(2 * v - 1);
      var r = 9 + Math.random() * 4.5;
      pos[i*3]     = r * Math.sin(phi) * Math.cos(theta);
      pos[i*3 + 1] = r * Math.sin(phi) * Math.sin(theta) * 0.72;
      pos[i*3 + 2] = r * Math.cos(phi);
    }
    var pg = new THREE.BufferGeometry();
    pg.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    group.add(new THREE.Points(pg, new THREE.PointsMaterial({
      color: 0xffffff, size: 0.115, transparent: true, opacity: 0.95,
      sizeAttenuation: true, depthWrite: false,
      blending: THREE.AdditiveBlending })));

    var core = new THREE.Mesh(new THREE.IcosahedronGeometry(6.4, 2),
      new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true,
        transparent: true, opacity: 0.26 }));
    group.add(core);
    var ring = new THREE.Mesh(new THREE.TorusGeometry(13.5, 0.035, 8, 220),
      new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 }));
    ring.rotation.x = Math.PI / 2.35; group.add(ring);

    var target = { x: 0, y: 0 }, current = { x: 0, y: 0 };
    window.addEventListener("pointermove", function (e) {
      target.x = (e.clientX / window.innerWidth - 0.5) * 0.5;
      target.y = (e.clientY / window.innerHeight - 0.5) * 0.5;
    }, { passive: true });
    window.addEventListener("resize", function () {
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
    var running = true;
    document.addEventListener("visibilitychange", function () {
      running = !document.hidden; if (running && !reduced) loop();
    });
    function frame(t) {
      current.x += (target.x - current.x) * 0.045;
      current.y += (target.y - current.y) * 0.045;
      group.rotation.y = t * 0.00006 + current.x;
      group.rotation.x = current.y * 0.6;
      core.rotation.y = -t * 0.00011;
      ring.rotation.z = t * 0.00004;
      camera.position.z = 26 + Math.sin(t * 0.00013) * 1.6;
      renderer.render(scene, camera);
    }
    function loop(t) { if (!running || reduced) return; frame(t || 0); requestAnimationFrame(loop); }
    if (reduced) frame(0); else loop(0);
  }

  /* ---- scroll reveal ---- */
  var io = ("IntersectionObserver" in window) ? new IntersectionObserver(function (es) {
    es.forEach(function (en) {
      if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
    });
  }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }) : null;
  function observe(nodes) {
    if (!io || reduced) { nodes.forEach(function (n) { n.classList.add("in"); }); return; }
    nodes.forEach(function (n) { io.observe(n); });
  }
  observe(document.querySelectorAll(".reveal"));

  /* ---- clock ---- */
  var clock = document.getElementById("clock"), stamp = document.getElementById("stamp");
  function tick() {
    var d = new Date(), t = d.toLocaleTimeString("en-GB", { hour12: false });
    if (clock) clock.textContent = "Live \\u00b7 " + t;
    if (stamp) stamp.textContent = d.toLocaleDateString("en-GB",
      { day: "2-digit", month: "short", year: "numeric" }) + " \\u00b7 " + t;
  }
  tick(); setInterval(tick, 1000);

  var cue = document.getElementById("cue");
  if (cue) window.addEventListener("scroll", function () {
    cue.style.opacity = window.scrollY > 80 ? "0" : "1";
  }, { passive: true });

  /* ---- fleet table: sort and filter over data embedded in the page ----
     The rows are server-rendered too, so the table is complete and readable
     before this runs and with JavaScript switched off entirely. */
  var seed = document.getElementById("fleet-data");
  if (seed) {
    var ROWS = JSON.parse(seed.textContent);
    var state = { key: "created_at", dir: -1, q: "" };
    var tbody = document.querySelector("#fleet tbody");
    var count = document.getElementById("count");
    var empty = document.getElementById("empty");

    function esc(s) {
      return String(s).replace(/[&<>"]/g, function (c) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
      });
    }
    function render() {
      var q = state.q.trim().toLowerCase();
      var rows = ROWS.filter(function (r) {
        return !q || r.model_id.toLowerCase().indexOf(q) > -1
                  || (r.publisher || "").toLowerCase().indexOf(q) > -1;
      });
      rows.sort(function (a, b) {
        var x = a[state.key], y = b[state.key];
        if (typeof x === "string") return x.localeCompare(y) * state.dir;
        return ((x || 0) - (y || 0)) * state.dir;
      });
      tbody.innerHTML = rows.map(function (r) {
        return "<tr>"
          + '<td class="name"><a href="/p/' + esc(r.slug) + '">' + esc(r.model_id) + "</a></td>"
          + "<td>" + esc(r.publisher || "\\u2014") + "</td>"
          + '<td><span class="grade" data-g="' + esc(r.grade) + '">' + esc(r.grade_label) + "</span></td>"
          + '<td class="num">' + Math.round(r.coverage * 100) + "%</td>"
          + '<td class="num">' + r.passes + "</td>"
          + "<td>" + esc(r.worst || "\\u2014") + "</td>"
          + '<td class="num">' + esc(r.issued) + "</td>"
          + "</tr>";
      }).join("");
      if (count) count.textContent = rows.length + (rows.length === 1 ? " passport" : " passports");
      if (empty) empty.hidden = rows.length > 0;
    }
    document.querySelectorAll("#fleet th").forEach(function (th) {
      function sort() {
        var k = th.dataset.key; if (!k) return;
        state = { key: k, dir: state.key === k ? -state.dir : 1, q: state.q };
        document.querySelectorAll("#fleet th").forEach(function (o) {
          if (o === th) o.setAttribute("aria-sort", state.dir === 1 ? "ascending" : "descending");
          else o.removeAttribute("aria-sort");
        });
        render();
      }
      th.addEventListener("click", sort);
      th.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); sort(); }
      });
    });
    var qbox = document.getElementById("q");
    if (qbox) qbox.addEventListener("input", function (e) { state.q = e.target.value; render(); });
  }

  (window.__threeReady || Promise.resolve(false)).then(function (ok) { if (ok) initScene(); });
})();
"""


def e(x) -> str:
    return html.escape(str(x if x is not None else ""), quote=True)


def _shell(title: str, desc: str, body: str, *, cue: bool = False) -> str:
    """Twitter card meta is deliberately absent. og: tags are kept: a passport's
    whole purpose is being forwarded to someone, and without them a shared link
    renders as a bare URL."""
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#000000">
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="manifest" href="/site.webmanifest">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
{FONTS}
<style>{CSS}</style>
</head><body>
<canvas id="scene" aria-hidden="true"></canvas>
<div id="scene-veil" aria-hidden="true"></div>
{body}
{'<div class="cue" id="cue"><span>Scroll</span><i></i></div>' if cue else ''}
<script>{SCENE_JS}</script>
<script>{APP_JS}</script>
</body></html>"""


def _bar(current: str = "") -> str:
    items = [("/", "Audit"), ("/fleet", "Fleet"), ("/standards", "Coverage")]
    nav = "".join(
        f'<li><a href="{href}"'
        f'{" aria-current=\"page\"" if href == current else ""}>{e(label)}</a></li>'
        for href, label in items)
    return f"""<header class="bar"><div class="bar-in">
  <a class="mark" href="/">Orqen<em>/</em>Systems</a>
  <ul class="nav">{nav}</ul>
  <p class="status"><span class="dot" aria-hidden="true"></span><span id="clock">&mdash;</span></p>
</div></header>"""


def _foot() -> str:
    return """<footer class="foot">
  <span>Orqen &middot; empirical AI bill of materials</span>
  <span><a href="/standards">Coverage</a> &middot;
        <a href="/.well-known/orqen-signing-key.json">Signing key</a> &middot;
        <a href="/api/standards">API</a></span>
  <span id="stamp">&mdash;</span>
</footer>"""


# --- landing -----------------------------------------------------------------
def landing_html(example: str = "meta-llama/Llama-3.1-8B-Instruct",
                 error: str = "", stats: dict | None = None) -> str:
    st = stats or {}
    err = (f'<div class="notice" role="alert"><b>Not accepted</b>{e(error)}</div>'
           if error else "")

    readout = "".join(
        f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in [
            ("Models audited", st.get("models", 0)),
            ("Passports issued", st.get("passports", 0)),
            ("Probe families", 4),
            ("Suite", st.get("suite", "probes-v2")),
        ])

    return _shell(
        "Orqen \u2014 measured behaviour for AI models",
        "Orqen runs an AI model, records what it actually did, and issues a "
        "shareable certificate of measured behaviour.",
        f"""{_bar("/")}
<main class="shell" id="top">
  <section class="head">
    <p class="eyebrow reveal">Empirical AI bill of materials</p>
    <h1 class="reveal">Every model ships with a description.
      <b>Almost none ship with a measurement.</b></h1>
    <p class="reveal">Existing bill-of-materials tooling reads what a model's
      authors declared. Orqen runs the model, records what it did, and names the
      documented incidents where models behaving this way have already caused
      harm. <strong>No account, no install, permanent URL.</strong></p>

    <form class="audit reveal" method="post" action="/audit">
      <label for="mid">Hugging Face model id</label>
      <input id="mid" name="model_id" required placeholder="org/model"
        spellcheck="false" autocomplete="off" autocapitalize="off">
      <button type="submit">Issue passport</button>
    </form>
    <p class="hint reveal">Or run the example:
      <a href="/audit?model_id={e(example)}">{e(example)}</a>
      &nbsp;&middot;&nbsp; about 20 seconds &nbsp;&middot;&nbsp;
      <a href="/fleet">see everything audited so far</a></p>
    {err}
    <dl class="readout reveal">{readout}</dl>
  </section>

  <section class="section">
    <div class="section-head reveal">
      <h2>What is measured</h2>
      <span>Black-box only</span>
    </div>
    <p class="lede reveal">No weights, no gradients, no privileged access &mdash;
      only what you could measure about a model you did not train and cannot see
      inside, which is the position nearly everyone deploying a model is in.
      Every figure carries a control condition and, where several passes were
      run, an interval.</p>
    <div class="tiles">
      <article class="tile reveal">
        <p class="tile-label"><span>Fairness</span><span>6 pairs + 3 controls</span></p>
        <p class="tile-value">4<span class="tile-unit">axes</span></p>
        <p class="tile-delta">One prompt rendered twice, differing only by name,
          pronoun, geography or age. Graded net of a within-group control that
          establishes the noise floor.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>Robustness</span><span>18 prompts</span></p>
        <p class="tile-value">2<span class="tile-unit">metrics</span></p>
        <p class="tile-delta">The same question asked three ways, plus whether a
          borderline refusal survives being rephrased.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>Calibration</span><span>14 items</span></p>
        <p class="tile-value">ECE<span class="tile-unit">+ hallucination</span></p>
        <p class="tile-delta">Stated confidence binned against measured accuracy.
          Four items have no true answer, where the correct response is to decline.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>Leakage</span><span>4 canaries</span></p>
        <p class="tile-value">8<span class="tile-unit">token run</span></p>
        <p class="tile-delta">Prompted with the opening of a known public text,
          measured by the longest verbatim run reproduced.</p>
      </article>
    </div>
  </section>

  <section class="section">
    <div class="section-head reveal">
      <h2>What this does not tell you</h2>
      <span>Stated plainly</span>
    </div>
    <div class="tiles">
      <article class="tile reveal">
        <p class="tile-label"><span>01</span></p>
        <p class="tile-delta" style="margin:0">A pass means this suite found
          nothing. Absence of a finding is not evidence of safety, and every
          certificate says so on its face.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>02</span></p>
        <p class="tile-delta" style="margin:0">Measurements describe the model as
          served on the issue date through one gateway. The same weights served
          elsewhere may read differently.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>03</span></p>
        <p class="tile-delta" style="margin:0">Where no reference cohort has been
          measured, limits express judgement against published frameworks. The
          passport names which basis it used.</p>
      </article>
      <article class="tile reveal">
        <p class="tile-label"><span>04</span></p>
        <p class="tile-delta" style="margin:0">Text in, text out. No vision, no
          tabular models, no continuous monitoring. The fingerprint schema is
          versioned to grow.</p>
      </article>
    </div>
    <p class="hint reveal" style="margin-top:calc(var(--sp)*8)">
      <a href="/standards">See exactly what Orqen supplies</a> against EU AI Act
      Annex IV, NIST AI RMF and the OWASP LLM Top 10 &mdash; including the nine
      points it supplies nothing toward.</p>
  </section>
  {_foot()}
</main>""", cue=True)


# --- fleet -------------------------------------------------------------------
GRADE_LABEL = {
    "red": "Outside spec", "amber": "Review", "indeterminate": "No call",
    "green": "Within spec", "insufficient": "Inconclusive",
}

TILE_METRICS = [
    ("fairness.excess_divergence", "Fairness, net of control", 0.08),
    ("robustness.refusal_instability", "Refusal instability", 0.10),
    ("calibration.ece", "Calibration error", 0.10),
    ("leakage.verbatim_rate", "Verbatim reproduction", 0.05),
]


def _spark(values: list[float], limit: float, w: int = 260, h: int = 44) -> str:
    """Distribution across the estate, sorted ascending, with the pass limit
    drawn as a dashed rule. A single audited model gives a flat line, which is
    honest: one point is not a distribution."""
    if not values:
        return ""
    lo, hi = min(values + [limit]), max(values + [limit])
    span = (hi - lo) or 1.0
    pad = 3

    def y(v):
        return h - pad - ((v - lo) / span) * (h - pad * 2)

    if len(values) == 1:
        d = f"M0,{y(values[0]):.2f} L{w},{y(values[0]):.2f}"
    else:
        d = " ".join(
            f"{'L' if i else 'M'}{(i / (len(values) - 1)) * w:.2f},{y(v):.2f}"
            for i, v in enumerate(values))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" preserveAspectRatio="none" '
            f'aria-hidden="true">'
            f'<path class="fill" d="{d} L{w},{h} L0,{h} Z"/><path d="{d}"/>'
            f'<line class="lim" x1="0" y1="{y(limit):.2f}" x2="{w}" y2="{y(limit):.2f}"/>'
            f'<line class="base" x1="0" y1="{h - .5}" x2="{w}" y2="{h - .5}"/></svg>')


def fleet_stats(rows: list[dict]) -> dict:
    """Aggregates for the readout and the landing page. Latest passport per
    model, so re-auditing one model does not skew the estate view."""
    latest: dict[str, dict] = {}
    for r in rows:                       # rows arrive newest-first
        latest.setdefault(r["model_id"], r)
    models = list(latest.values())
    covs = [(m.get("scores") or {}).get("coverage", 0) or 0 for m in models]
    return {
        "passports": len(rows),
        "models": len(models),
        "mean_coverage": (statistics.mean(covs) if covs else 0),
        "with_red": sum(1 for m in models
                        if (m.get("scores") or {}).get("overall") == "red"),
        "latest": models,
    }


def _fleet_rows(models: list[dict]) -> list[dict]:
    out = []
    for m in models:
        sc = m.get("scores") or {}
        fp = m.get("fingerprint") or {}
        findings = sc.get("findings") or []
        worst = next((f["metric"] for f in findings
                      if f.get("grade") in ("red", "amber", "indeterminate")), "")
        grade = sc.get("overall", "insufficient")
        out.append({
            "slug": m["slug"],
            "model_id": m["model_id"],
            "publisher": m["model_id"].split("/")[0] if "/" in m["model_id"] else "",
            "grade": grade,
            "grade_label": GRADE_LABEL.get(grade, grade),
            "coverage": sc.get("coverage", 0) or 0,
            "passes": fp.get("replicates", 1) or 1,
            "worst": worst,
            "created_at": m["created_at"],
            "issued": _dt.datetime.utcfromtimestamp(m["created_at"]).strftime("%d %b %H:%M"),
        })
    return out


def fleet_html(rows: list[dict], range_label: str = "All time",
               ranges: list[tuple] | None = None, active: str = "ALL") -> str:
    stats = fleet_stats(rows)
    frows = _fleet_rows(stats["latest"])

    readout = "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in [
        ("Models audited", stats["models"]),
        ("Passports issued", stats["passports"]),
        ("Mean coverage", f"{round(stats['mean_coverage'] * 100)}%"),
        ("Outside spec", f"{stats['with_red']} / {stats['models']}"),
    ])

    tiles = []
    for key, label, limit in TILE_METRICS:
        vals = sorted(
            (m.get("fingerprint") or {}).get("metrics", {}).get(key)
            for m in stats["latest"]
            if (m.get("fingerprint") or {}).get("metrics", {}).get(key) is not None)
        vals = [v for v in vals if v is not None]
        if not vals:
            tiles.append(f"""<article class="tile reveal">
  <p class="tile-label"><span>{e(label)}</span><span>no data</span></p>
  <p class="tile-value">&mdash;</p>
  <p class="tile-delta">No passport has reported this metric yet.</p></article>""")
            continue
        med = statistics.median(vals)
        over = sum(1 for v in vals if v > limit)
        tiles.append(f"""<article class="tile reveal" tabindex="0">
  <p class="tile-label"><span>{e(label)}</span><span>median</span></p>
  <p class="tile-value">{med:.3f}</p>
  {_spark(vals, limit)}
  <p class="tile-delta" data-dir="{'up' if over else 'down'}">
    {over} of {len(vals)} model(s) above the {limit:g} pass limit
    &middot; dashed rule is the limit</p></article>""")

    body_rows = "".join(f"""<tr>
  <td class="name"><a href="/p/{e(r['slug'])}">{e(r['model_id'])}</a></td>
  <td>{e(r['publisher'] or '—')}</td>
  <td><span class="grade" data-g="{e(r['grade'])}">{e(r['grade_label'])}</span></td>
  <td class="num">{round(r['coverage'] * 100)}%</td>
  <td class="num">{r['passes']}</td>
  <td>{e(r['worst'] or '—')}</td>
  <td class="num">{e(r['issued'])}</td></tr>""" for r in frows)

    range_buttons = "".join(
        f'<button type="button" onclick="location.href=\'/fleet?range={k}\'" '
        f'aria-pressed="{str(k == active).lower()}">{e(v)}</button>'
        for k, v in (ranges or []))

    empty_state = """<p class="empty" id="empty" {}>
  <strong>No passports in this range.</strong>
  Issue one from the <a href="/">audit page</a> and it will appear here.</p>""".format(
        "" if not frows else "hidden")

    return _shell(
        "Orqen \u2014 fleet",
        "Every model Orqen has audited, with its determination, coverage and "
        "worst measured axis.",
        f"""{_bar("/fleet")}
<main class="shell" id="top">
  <section class="head">
    <p class="eyebrow reveal">Fleet</p>
    <h1 class="reveal">Every model measured, <b>one surface.</b></h1>
    <p class="reveal">One row per model, showing its most recent passport.
      Re-auditing a model replaces its row rather than adding one, so this is the
      current state of the estate rather than a log.</p>
    <dl class="readout reveal">{readout}</dl>
  </section>

  <section class="section">
    <div class="section-head reveal">
      <h2>Measured distribution</h2>
      <span>{e(range_label)}</span>
    </div>
    <p class="lede reveal">Each tile is one graded metric across every audited
      model, sorted ascending. The dashed rule is the pass limit &mdash; the
      shape above it is how much of the estate is out of specification on that
      axis.</p>
    <div class="tiles">{''.join(tiles)}</div>
  </section>

  <section class="section">
    <div class="section-head reveal">
      <h2>Passports</h2>
      <span>Sort by any column</span>
    </div>
    <div class="filter reveal">
      <label class="visually-hidden" for="q">Filter models</label>
      <input id="q" type="search" placeholder="Filter by model or publisher"
        autocomplete="off" spellcheck="false">
      <span class="count" id="count">{len(frows)} passport{'' if len(frows) == 1 else 's'}</span>
      {f'<div class="ranges" role="group" aria-label="Audit range">{range_buttons}</div>'
       if range_buttons else ''}
    </div>
    <div class="table-wrap reveal">
      <table id="fleet">
        <thead><tr>
          <th data-key="model_id"   scope="col" tabindex="0">Model</th>
          <th data-key="publisher"  scope="col" tabindex="0">Publisher</th>
          <th data-key="grade"      scope="col" tabindex="0">Determination</th>
          <th data-key="coverage"   scope="col" tabindex="0">Coverage</th>
          <th data-key="passes"     scope="col" tabindex="0">Passes</th>
          <th data-key="worst"      scope="col" tabindex="0">Worst axis</th>
          <th data-key="created_at" scope="col" tabindex="0" aria-sort="descending">Issued</th>
        </tr></thead>
        <tbody>{body_rows}</tbody>
      </table>
      {empty_state}
    </div>
    <script type="application/json" id="fleet-data">{json.dumps(frows)}</script>
  </section>
  {_foot()}
</main>""")


def error_html(code: int, message: str) -> str:
    return _shell(f"Orqen \u2014 {code}", message, f"""{_bar()}
<main class="shell" id="top">
  <section class="head">
    <p class="eyebrow">{code}</p>
    <h1>{'Nothing here.' if code == 404 else 'That did not work.'}</h1>
    <p>{e(message)}</p>
    <form class="audit" method="post" action="/audit">
      <label for="mid">Hugging Face model id</label>
      <input id="mid" name="model_id" required placeholder="org/model" spellcheck="false">
      <button type="submit">Issue passport</button>
    </form>
    <p class="hint"><a href="/fleet">Or browse everything audited so far</a></p>
  </section>
  {_foot()}
</main>""")
