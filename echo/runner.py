"""Connect observations to decisions; export reproducible evidence."""
import json
from pathlib import Path
from .config import distance
from .environment import Environment
from .planner import Agent


class Mission:
    def __init__(self, config, baseline=False):
        self.env = Environment(config)
        self.agent = Agent(self.env.public_briefing(), baseline=baseline)
        self.initial = self.env.observation()
        self.agent.observe(self.initial)
        self.trace = []
        self.path = [self.initial["position"]]
        self.evidence = []
        self.name = self.env.public_briefing()["name"]
        self.agent_name = "baseline" if baseline else "echo"

    def step(self):
        if self.env.outcome != "searching":
            return self.snapshot()
        decision = self.agent.decide()
        observation = self.env.step(decision["action"])
        self.agent.observe(observation)
        if observation.get("signal"):
            self.evidence.append({"type": "scan", **observation["signal"]})
        if observation.get("evidence"):
            self.evidence.append({"type": "clue", **observation["evidence"]})
        self.path.append(observation["position"])
        self.trace.append({"step": len(self.trace)+1, "decision": decision, "observation": observation,
                           "belief_after": self.agent.belief.summary()})
        return self.snapshot()

    def run(self):
        while self.env.outcome == "searching":
            self.step()
        return self.report()

    def report(self):
        summary = self.agent.belief.summary()
        found = self.env.outcome == "found"
        recommendation = {"ready": "Rendezvous with EVE and return together.",
                          "stranded": "Bring a power supply to EVE's confirmed location.",
                          "damaged": "Request a repair/recovery team at EVE's confirmed location."}
        status = max(summary["status"], key=summary["status"].get)
        return {"mission": self.name, "agent": self.agent_name, "outcome": self.env.outcome,
                "confirmed": found, "estimated_location": summary["location"],
                "confidence": summary["confidence"], "estimated_status": status if max(summary["status"].values()) > 1/3+.001 else "unknown",
                "status_probabilities": summary["status"], "actions": self.env.actions,
                "energy_consumed": self.env.energy_used, "battery_remaining": self.env.battery,
                "time_used": self.env.public_briefing()["time_budget"]-self.env.time,
                "time_remaining": self.env.time, "scans": sum(self.agent.scans.values()),
                "clues_investigated": len(self.agent.investigated), "evidence": self.evidence,
                "belief_recoveries": summary["recoveries"],
                "key_decisions": [{"step": t["step"], **t["decision"]} for t in self.trace if t["decision"]["target_changed"] or t["decision"]["action"]["kind"] in ["recharge", "end"]],
                "recommended_next_step": recommendation[status] if found else "Relay the best estimate and uncertainty; obtain fresh evidence or a larger search budget. EVE is not confirmed."}

    def metrics(self):
        report = self.report()
        truth = self.env.evaluator_truth()
        return {key: report[key] for key in ["agent", "outcome", "actions", "energy_consumed", "scans"]} | {
            "success": report["confirmed"], "localization_error": distance(report["estimated_location"], truth["eve"])}

    def snapshot(self):
        return {"name": self.name, "width": self.agent.info["width"], "height": self.agent.info["height"],
                "terrain": [{"cell": list(c), "kind": k} for c, k in self.agent.known.items()],
                "belief": [{"cell": list(c), "probability": p} for c, p in self.agent.belief.probabilities.items()],
                "summary": self.agent.belief.summary(), "position": list(self.agent.position),
                "clues": [list(c) for c in sorted(self.agent.clues)], "investigated": [list(c) for c in sorted(self.agent.investigated)],
                "path": self.path, "battery": self.env.battery, "capacity": self.agent.info["battery_capacity"],
                "time_remaining": self.env.time, "time_budget": self.agent.info["time_budget"],
                "actions": self.env.actions, "outcome": self.env.outcome,
                "latest": self.trace[-1] if self.trace else None,
                "report": self.report() if self.env.outcome != "searching" else None}

    def export(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        (folder/"trace.jsonl").write_text("\n".join(json.dumps(t, sort_keys=True) for t in self.trace)+"\n")
        (folder/"initial.json").write_text(json.dumps({"observation": self.initial, "briefing": self.agent.info}, indent=2)+"\n")
        report = self.report()
        (folder/"report.json").write_text(json.dumps(report, indent=2)+"\n")
        (folder/"report.md").write_text(f"# {self.name}\n\nOutcome: **{report['outcome']}**. Confirmed: **{report['confirmed']}**.\n\n"
            f"Estimated location: {report['estimated_location']}; confidence: {report['confidence']:.1%}. "
            f"Status: {report['estimated_status']}.\n\n"
            f"{report['actions']} actions · {report['energy_consumed']} energy used · {report['scans']} scans · {report['clues_investigated']} clues investigated.\n\n"
            f"{report['recommended_next_step']}\n\nFull observations and decisions: [trace.jsonl](trace.jsonl). Evidence and key decisions: [report.json](report.json).\n")
        (folder/"path.svg").write_text(path_svg(self.snapshot()))


def path_svg(state):
    import html
    size, pad = 34, 24
    width, height = state["width"]*size+pad*2, state["height"]*size+pad*2+50
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
             f'<rect width="100%" height="100%" fill="#eee9df"/><text x="24" y="28" fill="#233c34" font-family="sans-serif" font-size="16">{html.escape(state["name"])} · observed map</text>']
    known = {tuple(t["cell"]): t["kind"] for t in state["terrain"]}
    for y in range(state["height"]):
        for x in range(state["width"]):
            kind = known.get((x, y))
            fill = {"#": "#64645b", ".": "#dcd8cd", "C": "#91b69c"}.get(kind, "#b8baaf")
            parts.append(f'<rect x="{pad+x*size}" y="{50+y*size}" width="32" height="32" rx="4" fill="{fill}"/>')
            if kind == "C":
                parts.append(f'<text x="{pad+x*size+10}" y="{50+y*size+23}" font-family="sans-serif">C</text>')
    points = " ".join(f"{pad+x*size+16},{50+y*size+16}" for x, y in state["path"])
    parts.append(f'<polyline points="{points}" fill="none" stroke="#ba6b39" stroke-width="3" opacity=".8"/>')
    for x, y in state["clues"]:
        parts.append(f'<circle cx="{pad+x*size+16}" cy="{50+y*size+16}" r="5" fill="#bb873b"/>')
    x, y = state["position"]
    parts.append(f'<circle cx="{pad+x*size+16}" cy="{50+y*size+16}" r="10" fill="#284f40" stroke="#fff" stroke-width="2"/>')
    parts.append('</svg>')
    return "".join(parts)
