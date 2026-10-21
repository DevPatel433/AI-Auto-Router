"""
Local dashboard + static report for the auto-router. Standard library only.

  python dashboard.py              # live dashboard at http://127.0.0.1:8000
  python dashboard.py --report     # writes report.html (self-contained, shareable)
  python dashboard.py --demo       # seed router_log.jsonl with sample tasks (route-only)

Live page: type a task, see which route it takes, and watch the charts update from router_log.jsonl.
"""
import argparse
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from router import Router

LOG = "router_log.jsonl"
SAMPLES = [
    "Write a Python function to merge two sorted lists", "Debug this SQL query that returns duplicates",
    "Implement a rolling Sharpe ratio in pandas", "Refactor this class to use dataclasses",
    "Compare recent papers on market regime detection", "Summarise the main ideas behind retrieval-augmented generation",
    "Why do volatility spikes cluster?", "Analyse the pros and cons of transformer vs LSTM forecasting",
    "Draft an email declining a meeting politely", "Write a short story about a trader who loses track of time",
    "Rewrite this paragraph in a friendlier tone", "Write a LinkedIn post announcing my new project",
    "hello", "Explain how this regex works and rewrite it more readable",
]

def avg(xs):
    return round(sum(xs) / len(xs), 2) if xs else 0

def compute_stats(path: str = LOG) -> dict:
    rows = []
    if os.path.exists(path):
        with open(path) as f:
            rows = [json.loads(l) for l in f if l.strip()]
    n = len(rows)
    cats, via = {}, {"llm": 0, "heuristic": 0}
    fallback = 0
    for r in rows:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
        via["llm" if r["classifier"].startswith("llm") else "heuristic"] += 1
        fallback += "fallback" in r["classifier"]
    return {
        "total": n,
        "categories": cats,
        "classifier": via,
        "fallbacks": fallback,
        "avg_classify_ms": avg([r["classify_ms"] for r in rows if "classify_ms" in r]),
        "avg_model_ms": avg([r["model_ms"] for r in rows if r.get("model_ms")]),
        "avg_confidence": round(sum(r["confidence"] for r in rows) / n, 2) if n else 0,
        "recent": rows[-15:][::-1],
    }

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Auto-Router Dashboard</title>
<style>
:root{--bg:#fafaf7;--card:#fff;--ink:#1d2b24;--mute:#6b7770;--line:#e3e6df;--c1:#2f6f4f;--c2:#3b6ea5;--c3:#b5651d}
@media(prefers-color-scheme:dark){:root{--bg:#131815;--card:#1b221e;--ink:#e8ede9;--mute:#97a39c;--line:#2d3832;--c1:#5fbf8f;--c2:#6aa6e0;--c3:#e0954f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif;padding:20px;max-width:980px;margin:auto}
h1{font-size:22px;margin:0 0 4px}p.sub{color:var(--mute);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:14px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:14px}
.kpi b{display:block;font-size:26px}.kpi span{color:var(--mute);font-size:13px}
input[type=text]{width:100%;padding:11px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);font-size:15px}
button{padding:9px 14px;border-radius:8px;border:1px solid var(--line);background:var(--c1);color:#fff;font-size:14px;cursor:pointer;margin:8px 8px 0 0}
button.alt{background:none;color:var(--ink)}label{font-size:13px;color:var(--mute)}
.bar{display:flex;align-items:center;gap:10px;margin:8px 0}.bar .n{width:80px}.bar .t{flex:1;background:var(--line);border-radius:6px;height:20px;overflow:hidden}
.bar .f{height:100%;border-radius:6px}.bar .v{width:70px;text-align:right;color:var(--mute);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13.5px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--mute);font-weight:600}
td.task{max-width:340px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.pill{padding:2px 8px;border-radius:99px;font-size:12px;color:#fff}.result{margin-top:12px;display:none}
.flow{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:var(--mute)}.flow b{color:var(--ink);border:1px solid var(--line);padding:4px 9px;border-radius:8px}
pre{white-space:pre-wrap;background:var(--bg);padding:10px;border-radius:8px;border:1px solid var(--line);font-size:13px}
</style></head><body>
<h1>AI Auto-Router</h1><p class="sub">One task &rarr; right model. Live routing decisions and statistics.</p>
<div class="card flow"><b>Incoming task</b>&rarr;<b>Classifier</b>&rarr;<b>Router</b>&rarr;<b>Coding model</b> / <b>Research model</b> / <b>Writing model</b>&rarr;<b>Audit log</b></div>
<div class="card" id="live"><input type="text" id="task" placeholder="Type a task, e.g. Write a function that dedupes a list">
<label><input type="checkbox" id="dry" checked> route only (don't call the specialist model)</label><br>
<button onclick="route()">Route it</button><button class="alt" onclick="demo()">Run 14 sample tasks</button>
<div class="result" id="result"></div></div>
<div class="kpis" id="kpis"></div>
<div class="card"><b>Tasks by route</b><div id="bars"></div></div>
<div class="card"><b>Recent decisions</b><table><thead><tr><th>Task</th><th>Route</th><th>Conf.</th><th>Via</th><th>Routing</th><th>Model</th></tr></thead><tbody id="rows"></tbody></table></div>
<script>
window.__DATA__=/*DATA*/null;
const COL={coding:'var(--c1)',research:'var(--c2)',writing:'var(--c3)'};
const $=id=>document.getElementById(id);
function kpi(v,l){const d=document.createElement('div');d.className='card kpi';d.innerHTML='<b></b><span></span>';d.firstChild.textContent=v;d.lastChild.textContent=l;return d}
function render(s){
 const k=$('kpis');k.innerHTML='';
 [[s.total,'tasks routed'],[s.avg_classify_ms+' ms','avg routing time'],[s.avg_model_ms?s.avg_model_ms+' ms':'n/a','avg model time'],[s.avg_confidence,'avg confidence'],[s.fallbacks,'fallback to default']].forEach(([v,l])=>k.appendChild(kpi(v,l)));
 const b=$('bars');b.innerHTML='';const max=Math.max(1,...Object.values(s.categories));
 ['coding','research','writing'].forEach(c=>{const v=s.categories[c]||0;const d=document.createElement('div');d.className='bar';
  d.innerHTML='<span class="n"></span><div class="t"><div class="f"></div></div><span class="v"></span>';
  d.querySelector('.n').textContent=c;d.querySelector('.f').style.cssText='width:'+(v/max*100)+'%;background:'+COL[c];
  d.querySelector('.v').textContent=v+(s.total?' ('+Math.round(v/s.total*100)+'%)':'');b.appendChild(d)});
 const t=$('rows');t.innerHTML='';
 s.recent.forEach(r=>{const tr=document.createElement('tr');
  [r.task,r.category,r.confidence,r.classifier,r.classify_ms+' ms',r.model_ms?r.model_ms+' ms':'-'].forEach((x,i)=>{const td=document.createElement('td');
   if(i==0){td.className='task';td.title=x}
   if(i==1){const p=document.createElement('span');p.className='pill';p.style.background=COL[x];p.textContent=x;td.appendChild(p)}else td.textContent=x;tr.appendChild(td)});t.appendChild(tr)});
}
async function load(){render(window.__DATA__||await (await fetch('/stats')).json())}
async function route(){const task=$('task').value.trim();if(!task)return;
 const r=await (await fetch('/route',{method:'POST',body:JSON.stringify({task,dry:$('dry').checked})})).json();
 const box=$('result');box.style.display='block';box.innerHTML='<div></div><pre></pre>';
 box.firstChild.textContent=r.category.toUpperCase()+' | confidence '+r.confidence+' | '+r.classifier+' -> '+r.model;
 box.lastChild.textContent=r.response||'(route only, no model call)';load()}
async function demo(){await fetch('/demo',{method:'POST'});load()}
if(window.__DATA__){$('live').style.display='none'}
load();
</script></body></html>"""

def build_report(path: str = "report.html") -> str:
    stats = compute_stats()
    for r in stats["recent"]:  # keep the static report free of model identifiers
        r.pop("model", None)
        r.pop("label", None)
    html = PAGE.replace("/*DATA*/null", json.dumps(stats))
    with open(path, "w") as f:
        f.write(html)
    return path

class Handler(BaseHTTPRequestHandler):
    router = None

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/stats":
            self._send(200, json.dumps(compute_stats()))
        else:
            self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/route":
            self._send(200, json.dumps(self.router.run(body["task"], bool(body.get("dry", True)))))
        elif self.path == "/demo":
            for t in SAMPLES:
                self.router.run(t, dry=True)
            self._send(200, json.dumps({"ok": True}))
        else:
            self._send(404, "{}")

    def log_message(self, *a):
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="write a static report.html")
    ap.add_argument("--demo", action="store_true", help="seed the log with sample tasks")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()
    if a.demo:
        r = Router()
        for t in SAMPLES:
            r.run(t, dry=True)
        print(f"Logged {len(SAMPLES)} sample routes to {LOG}")
        if not a.report:
            return
    if a.report:
        print("Wrote", build_report())
        return
    Handler.router = Router()
    url = f"http://127.0.0.1:{a.port}"
    print("Dashboard running at", url, "(Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()

if __name__ == "__main__":
    main()
