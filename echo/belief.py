"""Finite Bayesian filter; all updates come from the observation boundary."""
import math
from .config import distance


def range_likelihood(reading, true_range, maximum, outlier_rate):
    normal = sum(weight for error, weight in [(-1, .2), (0, .6), (1, .2)]
                 if max(0, min(maximum, true_range+error)) == reading)
    return (1-outlier_rate)*normal + outlier_rate/(maximum+1)


class Belief:
    def __init__(self, info):
        self.width, self.height = info["width"], info["height"]
        self.probabilities = {(x, y): 1/(self.width*self.height) for y in range(self.height) for x in range(self.width)}
        self.excluded = set()
        self.status = {s: 1/3 for s in ["ready", "stranded", "damaged"]}
        self.recoveries = 0
        initial = info.get("initial_signal")
        if initial:
            age = max(0, info["mission_time"]-initial["timestamp"])
            reliability = .85*initial["strength"]*math.exp(-age/20)
            start = info["start"]
            def hint(cell):
                if "coordinates" in initial:
                    return math.exp(-distance(cell, initial["coordinates"])**2/8)
                dx, dy = cell[0]-start[0], cell[1]-start[1]
                projection = {"N": -dy, "E": dx, "S": dy, "W": -dx}[initial["direction"]]
                return 1 if projection > 0 else .1
            self.update({c: (1-reliability)+reliability*hint(c)*8 for c in self.probabilities})

    def update(self, likelihood):
        # Log weights prevent repeated multiplication from underflowing to all zero.
        logs = {c: math.log(max(p, 1e-300))+math.log(likelihood[c])
                for c, p in self.probabilities.items() if c not in self.excluded and likelihood.get(c, 0) > 0}
        if not logs:
            candidates = [c for c in self.probabilities if c not in self.excluded]
            if not candidates:
                raise ValueError("Observation contradicts every possible location")
            self.recoveries += 1
            logs = {c: 0 for c in candidates}
        peak = max(logs.values())
        weights = {c: math.exp(v-peak) for c, v in logs.items()}
        total = sum(weights.values())
        self.probabilities = {c: weights.get(c, 0)/total for c in self.probabilities}

    def observe(self, obs):
        contact = obs.get("contact")
        if contact:
            location = tuple(contact["location"])
            self.probabilities = {c: float(c == location) for c in self.probabilities}
            self.status = {s: float(s == contact["status"]) for s in self.status}
            return
        self.excluded.add(tuple(obs["position"]))
        self.excluded.update(tuple(t["cell"]) for t in obs["terrain"] if t["kind"] == "#")
        self.update({c: 1 for c in self.probabilities})
        signal = obs.get("signal") or obs.get("evidence", {}).get("signal")
        if signal:
            self.update({c: range_likelihood(signal["range"], distance(c, signal["origin"]), self.width+self.height-2, signal["outlier_rate"])
                         for c in self.probabilities})
        evidence = obs.get("evidence")
        if evidence:
            weights = {s: p*(.8 if s == evidence["status_hint"] else .1) for s, p in self.status.items()}
            total = sum(weights.values())
            self.status = {s: p/total for s, p in weights.items()}

    def summary(self):
        cell = max(self.probabilities, key=self.probabilities.get)
        return {"location": list(cell), "confidence": self.probabilities[cell],
                "entropy_bits": -sum(p*math.log2(p) for p in self.probabilities.values() if p > 0),
                "status": dict(self.status), "recoveries": self.recoveries}
