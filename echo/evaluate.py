"""Paired, reproducible evaluation. Both agents get identical public interfaces."""
import csv
import json
from collections import Counter
from pathlib import Path
from .config import generate
from .runner import Mission


def evaluate(count=30, output="results/benchmark", start_seed=100):
    rows = []
    for seed in range(start_seed, start_seed+count):
        config = generate(seed)
        for baseline in [False, True]:
            mission = Mission(config, baseline)
            mission.run()
            rows.append({"seed": seed, **mission.metrics()})
    folder = Path(output)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/"runs.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for name in ["echo", "baseline"]:
        group = [r for r in rows if r["agent"] == name]
        summary[name] = {"missions": count, "success_rate": sum(r["success"] for r in group)/count,
                         **{"mean_"+key: sum(r[key] for r in group)/count for key in ["actions", "energy_consumed", "scans", "localization_error"]},
                         "outcomes": dict(Counter(r["outcome"] for r in group))}
    (folder/"summary.json").write_text(json.dumps(summary, indent=2)+"\n")
    chart = ['<svg xmlns="http://www.w3.org/2000/svg" width="700" height="210" viewBox="0 0 700 210"><rect width="700" height="210" fill="#eee9df"/><g font-family="sans-serif" fill="#263d34"><text x="24" y="32" font-size="20">Paired generated missions · contact success</text>']
    for i, name in enumerate(["echo", "baseline"]):
        y = 66+i*58
        rate = summary[name]["success_rate"]
        chart.append(f'<text x="24" y="{y+23}">{name.upper()}</text><rect x="130" y="{y}" width="{rate*450}" height="32" rx="4" fill="{"#416958" if i == 0 else "#a18257"}"/><text x="{140+rate*450}" y="{y+23}">{rate:.0%}</text>')
    chart.append(f'<text x="24" y="194">{count} seeds ({start_seed}–{start_seed+count-1}); same maps and resource budgets</text></g></svg>')
    (folder/"success.svg").write_text("".join(chart))
    return summary
