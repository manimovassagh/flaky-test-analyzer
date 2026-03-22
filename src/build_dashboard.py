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


DASHBOARD_TEMPLATE = Path(__file__).parent.parent / "notebooks" / "dashboard.html"


def build_html(data: dict) -> str:
    # Read the existing dashboard template and inject fresh data
    tmpl = DASHBOARD_TEMPLATE.read_text()
    # Replace the data constant
    marker_start = "const D = "
    marker_end   = ";\n"
    i = tmpl.index(marker_start) + len(marker_start)
    j = tmpl.index(marker_end, i) + len(marker_end)
    return tmpl[:i] + json.dumps(data) + ";\n" + tmpl[j:]


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
