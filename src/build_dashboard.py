"""
Load all TRX files from data/runs/, compute metrics, write dashboard.html.

Usage:
    uv run python src/build_dashboard.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from trx_parser import load_all

DATA_DIR  = Path("data/runs")
OUT_HTML  = Path("docs/index.html")   # docs/ = GitHub Pages root
OUT_JSON  = Path("data/dashboard.json")

OUT_HTML.parent.mkdir(parents=True, exist_ok=True)


def compute(data_dir: Path) -> dict:
    raw = load_all(data_dir)
    if not raw:
        raise SystemExit(f"No TRX files found in {data_dir}")

    df = pd.DataFrame([{
        "run_id":      r.run_id,
        "test_name":   r.test_name,
        "outcome":     r.outcome,
        "duration_ms": r.duration_ms,
    } for r in raw])

    df["failed"] = (df["outcome"] == "Failed").astype(int)
    run_stats = (df.groupby("run_id")
                   .agg(tests=("test_name", "count"), fails=("failed", "sum"))
                   .reset_index()
                   .sort_values("run_id")
                   .reset_index(drop=True))

    test_rate = (df.groupby("test_name")["failed"]
                   .agg(["sum", "count"])
                   .assign(rate=lambda d: d["sum"] / d["count"]))
    flaky  = test_rate[(test_rate["rate"] >= 0.05) & (test_rate["rate"] < 0.8)]
    broken = test_rate[test_rate["rate"] >= 0.8]
    stable = test_rate[test_rate["rate"] < 0.05]

    top15  = flaky.sort_values("rate", ascending=False).head(15)

    runner_tbl = (df[df["failed"] == 1]
                  .groupby("run_id")["test_name"]
                  .agg(Fails="count", tests=list)
                  .reset_index()
                  .rename(columns={"run_id": "Runner"})
                  .sort_values("Fails", ascending=False)
                  .reset_index(drop=True))
    runner_tbl["tests"] = runner_tbl["tests"].apply(lambda x: sorted(set(x)))

    pass_rate = 1 - df["failed"].sum() / len(df)

    return {
        "kpis": {
            "runs":          int(run_stats.shape[0]),
            "tests_per_run": int(run_stats["tests"].mean()),
            "avg_fails":     round(float(run_stats["fails"].mean()), 1),
            "pass_rate":     f"{pass_rate:.2%}",
            "flaky":         int(len(flaky)),
            "broken":        int(len(broken)),
        },
        "classification": {
            "stable": int(len(stable)),
            "flaky":  int(len(flaky)),
            "broken": int(len(broken)),
        },
        "runs": {
            "labels": list(range(len(run_stats))),
            "fails":  run_stats["fails"].tolist(),
            "avg":    round(float(run_stats["fails"].mean()), 1),
        },
        "top_flaky": {
            "names": [n.rsplit("_", 1)[0][-32:] for n in top15.index],
            "rates": [round(v * 100, 1) for v in top15["rate"].tolist()],
        },
        "runner_table": [
            {"runner": row["Runner"], "fails": int(row["Fails"]), "tests": row["tests"]}
            for _, row in runner_tbl.iterrows()
        ],
    }


def build_html(data: dict) -> str:
    """Return a self-contained dashboard HTML string with data embedded."""
    return _TEMPLATE.replace("__DATA_PLACEHOLDER__", json.dumps(data))


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Test Health Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
<style>
:root{
  --bg:#09090f;--surface:#12121c;--card:#181828;--border:#1e1e30;
  --teal:#00e5c3;--teal-dim:#00b89a;--teal-glow:rgba(0,229,195,.15);
  --amber:#f59e0b;--red:#ef4444;--green:#22c55e;
  --txt:#e2e8f0;--txt-muted:#64748b;--txt-dim:#475569;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--txt);font-family:'Syne',sans-serif;min-height:100vh;overflow-x:hidden}

/* scan-line texture */
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,229,195,.012) 2px,rgba(0,229,195,.012) 4px);
}

/* teal grid */
body::after{
  content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background-image:linear-gradient(rgba(0,229,195,.04) 1px,transparent 1px),linear-gradient(90deg,rgba(0,229,195,.04) 1px,transparent 1px);
  background-size:60px 60px;
}

.shell{position:relative;z-index:1;max-width:1440px;margin:0 auto;padding:32px 24px}

/* ── HEADER ── */
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:40px;padding-bottom:20px;border-bottom:1px solid var(--border)}
.brand{display:flex;align-items:center;gap:12px}
.brand-dot{width:10px;height:10px;border-radius:50%;background:var(--teal);box-shadow:0 0 12px var(--teal)}
.brand-name{font-size:18px;font-weight:800;letter-spacing:.04em;text-transform:uppercase;color:var(--teal)}
.brand-sub{font-size:11px;font-weight:400;color:var(--txt-muted);letter-spacing:.08em;text-transform:uppercase;margin-top:2px}
.ts{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--txt-muted)}

/* ── KPI CARDS ── */
.kpi-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-bottom:32px}
.kpi{
  background:var(--card);border:1px solid var(--border);border-radius:12px;
  padding:20px 18px 16px;position:relative;overflow:hidden;
  transition:transform .2s,border-color .2s;
}
.kpi:hover{transform:translateY(-2px);border-color:rgba(0,229,195,.25)}
.kpi::after{content:'';position:absolute;bottom:0;left:0;right:0;height:3px;background:var(--accent,var(--teal));opacity:.7}
.kpi-label{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:var(--txt-muted);margin-bottom:10px}
.kpi-value{font-family:'JetBrains Mono',monospace;font-size:32px;font-weight:600;color:var(--txt);line-height:1}
.kpi-value.small{font-size:22px}

/* ── SECTION GRID ── */
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.grid-3{display:grid;grid-template-columns:1fr 1.4fr 1.4fr;gap:20px;margin-bottom:20px}
@media(max-width:900px){.grid-2,.grid-3{grid-template-columns:1fr}}

/* ── GLASS CARD ── */
.card{
  background:var(--card);border:1px solid var(--border);border-radius:14px;
  padding:22px;overflow:hidden;
}
.card-title{
  font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;
  color:var(--teal);margin-bottom:18px;display:flex;align-items:center;gap:8px
}
.card-title::before{content:'';display:block;width:3px;height:14px;background:var(--teal);border-radius:2px}

/* ── STAT TABLE ── */
.stat-table{width:100%;border-collapse:collapse}
.stat-table tr{border-bottom:1px solid var(--border)}
.stat-table tr:last-child{border-bottom:none}
.stat-table td{padding:9px 0;font-size:13px}
.stat-table td:first-child{color:var(--txt-muted);font-size:11px;letter-spacing:.05em;text-transform:uppercase}
.stat-table td:last-child{text-align:right;font-family:'JetBrains Mono',monospace;font-weight:600;color:var(--txt)}

/* ── RUNNER TABLE ── */
.runner-table{width:100%;border-collapse:collapse;font-size:12px}
.runner-table thead th{
  font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--txt-muted);padding:0 8px 10px;text-align:left;border-bottom:1px solid var(--border)
}
.runner-table tbody tr{border-bottom:1px solid rgba(255,255,255,.04)}
.runner-table tbody tr:hover{background:rgba(0,229,195,.03)}
.runner-table td{padding:9px 8px;vertical-align:top}
.runner-id{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--txt-dim)}
.fail-chip{
  display:inline-block;padding:2px 8px;border-radius:20px;
  font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;
}
.chip-high{background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.3)}
.chip-mid {background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3)}
.chip-low {background:rgba(34,197,94,.15) ;color:#22c55e;border:1px solid rgba(34,197,94,.3)}
.test-list{color:var(--txt-muted);font-size:11px;line-height:1.6}

/* ── FLAKY TABLE ── */
.flaky-table{width:100%;border-collapse:collapse;font-size:12px}
.flaky-table thead th{
  font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--txt-muted);padding:0 8px 10px;text-align:left;border-bottom:1px solid var(--border)
}
.flaky-table tbody tr{border-bottom:1px solid rgba(255,255,255,.04)}
.flaky-table tbody tr:hover{background:rgba(0,229,195,.03)}
.flaky-table td{padding:8px 8px;vertical-align:middle}
.rate-bar-bg{background:rgba(255,255,255,.06);border-radius:4px;height:6px;width:100%;margin-top:4px;overflow:hidden}
.rate-bar-fill{height:100%;border-radius:4px;background:var(--teal)}
.rate-pct{font-family:'JetBrains Mono',monospace;font-size:11px;font-weight:600;color:var(--amber)}

footer{margin-top:48px;padding-top:20px;border-top:1px solid var(--border);
  text-align:center;font-size:11px;color:var(--txt-muted);letter-spacing:.05em}
</style>
</head>
<body>
<div class="shell">

<header>
  <div class="brand">
    <div class="brand-dot" id="live-dot"></div>
    <div>
      <div class="brand-name">Test Health Dashboard</div>
      <div class="brand-sub">Playwright .NET · Flaky Test Analysis</div>
    </div>
  </div>
  <div class="ts" id="ts">—</div>
</header>

<div class="kpi-row" id="kpi-row"></div>

<div class="grid-3">
  <div class="card">
    <div class="card-title">Classification</div>
    <div id="chart-donut" style="height:300px"></div>
  </div>
  <div class="card">
    <div class="card-title">Failures per Run</div>
    <div id="chart-bar" style="height:300px"></div>
  </div>
  <div class="card">
    <div class="card-title">Top 15 Flaky Tests</div>
    <div id="chart-flaky" style="height:300px"></div>
  </div>
</div>

<div class="grid-2">
  <div class="card">
    <div class="card-title">Suite Metrics</div>
    <table class="stat-table" id="stat-table"></table>
  </div>
  <div class="card">
    <div class="card-title">Top Flaky — Detail</div>
    <table class="flaky-table" id="flaky-table">
      <thead><tr><th>Test</th><th style="text-align:right">Fail Rate</th></tr></thead>
      <tbody id="flaky-tbody"></tbody>
    </table>
  </div>
</div>

<div class="card">
  <div class="card-title">Per-Runner Failures</div>
  <div style="max-height:480px;overflow-y:auto;border-radius:6px">
    <table class="runner-table" id="runner-table">
      <thead style="position:sticky;top:0;background:var(--card);z-index:1">
        <tr><th>Run ID</th><th>Failures</th><th>Failing Tests</th></tr>
      </thead>
      <tbody id="runner-tbody"></tbody>
    </table>
  </div>
</div>

<footer>Generated &middot; <span id="gen-ts">—</span></footer>

</div><!-- .shell -->

<script>
const D = __DATA_PLACEHOLDER__;

/* timestamp */
const now = new Date();
const fmt = d => d.toLocaleString('en-GB',{hour12:false,year:'numeric',month:'short',day:'2-digit',hour:'2-digit',minute:'2-digit'});
document.getElementById('ts').textContent = fmt(now);
document.getElementById('gen-ts').textContent = fmt(now);

/* live-dot pulse */
const dot = document.getElementById('live-dot');
setInterval(()=>dot.style.opacity = dot.style.opacity==='0'?'1':'0', 800);

/* KPI cards */
const KPI_CFG = [
  {key:'runs',       label:'Runs Analysed', accent:'var(--teal)'},
  {key:'tests_per_run', label:'Tests / Run', accent:'var(--teal)'},
  {key:'avg_fails',  label:'Avg Fails / Run', accent:'var(--amber)'},
  {key:'pass_rate',  label:'Pass Rate',      accent:'var(--green)'},
  {key:'flaky',      label:'Flaky Tests',    accent:'var(--amber)'},
  {key:'broken',     label:'Broken Tests',   accent:'var(--red)'},
];
const row = document.getElementById('kpi-row');
KPI_CFG.forEach(cfg => {
  const v = D.kpis[cfg.key];
  const small = typeof v === 'string' && v.length > 5;
  const el = document.createElement('div');
  el.className = 'kpi';
  el.style.setProperty('--accent', cfg.accent);
  el.innerHTML = `<div class="kpi-label">${cfg.label}</div><div class="kpi-value${small?' small':''}" data-target="${v}">${typeof v==='number'?0:v}</div>`;
  row.appendChild(el);
});

/* count-up animation */
document.querySelectorAll('.kpi-value[data-target]').forEach(el => {
  const raw = el.dataset.target;
  if (isNaN(raw)) return;
  const target = parseFloat(raw);
  const isFloat = raw.includes('.');
  let start = null;
  const step = ts => {
    if (!start) start = ts;
    const p = Math.min((ts - start) / 900, 1);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = isFloat ? (target * ease).toFixed(1) : Math.round(target * ease);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
});

/* Plotly shared config */
const PL = {displayModeBar:false, responsive:true};
const dark = {paper_bgcolor:'transparent', plot_bgcolor:'transparent', font:{color:'#94a3b8',family:'JetBrains Mono',size:10}};

/* Donut */
const cls = D.classification;
Plotly.newPlot('chart-donut',[{
  type:'pie', hole:.52,
  labels:[`Stable (${cls.stable})`,`Flaky (${cls.flaky})`,`Broken (${cls.broken})`],
  values:[cls.stable, cls.flaky, cls.broken],
  marker:{colors:['#22c55e','#f59e0b','#ef4444']},
  textinfo:'label+percent', textfont:{size:11},
  hovertemplate:'%{label}<br>%{value} tests<extra></extra>',
}],{
  ...dark, margin:{t:20,b:20,l:20,r:20}, height:300,
  showlegend:false,
},PL);

/* Bar — fails per run */
const fails = D.runs.fails;
const avg   = D.runs.avg;
const colors = fails.map(v => v >= avg*1.5 ? '#ef4444' : v >= avg ? '#f59e0b' : '#22c55e');
Plotly.newPlot('chart-bar',[{
  type:'bar', x:D.runs.labels, y:fails,
  marker:{color:colors}, hovertemplate:'Run %{x}<br>%{y} fails<extra></extra>',
},{
  type:'scatter', mode:'lines',
  x:[0, fails.length-1], y:[avg, avg],
  line:{color:'#00e5c3', width:1.5, dash:'dot'},
  hovertemplate:`avg ${avg}<extra></extra>`,
}],{
  ...dark, margin:{t:20,b:40,l:40,r:20}, height:300,
  xaxis:{showgrid:false, zeroline:false, title:{text:'Run #', font:{size:10}}},
  yaxis:{showgrid:true, gridcolor:'rgba(255,255,255,.05)', zeroline:false, title:{text:'Failures', font:{size:10}}},
  showlegend:false,
},PL);

/* Horizontal bar — top flaky */
Plotly.newPlot('chart-flaky',[{
  type:'bar', orientation:'h',
  x: D.top_flaky.rates,
  y: D.top_flaky.names,
  marker:{color:'#f59e0b'},
  text: D.top_flaky.rates.map(v=>v+'%'),
  textposition:'outside', cliponaxis:false,
  hovertemplate:'%{y}<br>%{x}%<extra></extra>',
}],{
  ...dark, margin:{t:20,b:40,l:10,r:60}, height:300,
  xaxis:{showgrid:false, zeroline:false, range:[0, Math.max(...D.top_flaky.rates)*1.3]},
  yaxis:{showgrid:false, automargin:true, tickfont:{size:9}},
},PL);

/* Suite metrics table */
const kpis = D.kpis;
const rows = [
  ['Runs Analysed', kpis.runs],
  ['Tests per Run',  kpis.tests_per_run],
  ['Avg Fails / Run', kpis.avg_fails],
  ['Pass Rate',      kpis.pass_rate],
  ['Flaky Tests',    kpis.flaky],
  ['Broken Tests',   kpis.broken],
];
const st = document.getElementById('stat-table');
rows.forEach(([label, val]) => {
  const tr = document.createElement('tr');
  tr.innerHTML = `<td>${label}</td><td>${val}</td>`;
  st.appendChild(tr);
});

/* Top flaky detail table */
const tb = document.getElementById('flaky-tbody');
D.top_flaky.names.forEach((name, i) => {
  const rate = D.top_flaky.rates[i];
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--txt-muted);word-break:break-all">${name}</td>
    <td style="text-align:right;min-width:80px">
      <span class="rate-pct">${rate}%</span>
      <div class="rate-bar-bg"><div class="rate-bar-fill" style="width:${rate}%"></div></div>
    </td>`;
  tb.appendChild(tr);
});

/* Runner table */
const rb = document.getElementById('runner-tbody');
const maxF = Math.max(...D.runner_table.map(r=>r.fails));
D.runner_table.forEach(r => {
  const ratio = r.fails / maxF;
  const chipCls = ratio >= .85 ? 'chip-high' : ratio >= .55 ? 'chip-mid' : 'chip-low';
  const tr = document.createElement('tr');
  const tests = r.tests.slice(0, 6).join('\n') + (r.tests.length > 6 ? `\n… +${r.tests.length-6} more` : '');
  tr.innerHTML = `
    <td><span class="runner-id">${r.runner}</span></td>
    <td><span class="fail-chip ${chipCls}">${r.fails}</span></td>
    <td><div class="test-list" style="white-space:pre">${tests}</div></td>`;
  rb.appendChild(tr);
});
</script>
</body>
</html>"""


if __name__ == "__main__":
    print(f"Loading TRX files from {DATA_DIR} …")
    data = compute(DATA_DIR)
    OUT_JSON.write_text(json.dumps(data, indent=2))

    html = build_html(data)
    OUT_HTML.write_text(html)

    print(f"Dashboard written to {OUT_HTML}")
    print(f"  Runs:   {data['kpis']['runs']}")
    print(f"  Flaky:  {data['kpis']['flaky']}")
    print(f"  Broken: {data['kpis']['broken']}")
