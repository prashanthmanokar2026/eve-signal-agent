"""Simulator truth. This module does not make planning decisions."""
import copy
import random
from .config import briefing, distance, neighbors, validate


class Environment:
    def __init__(self, config):
        self._config = copy.deepcopy(validate(config))
        self._rng = random.Random(self._config["seed"])
        self.position = tuple(self._config["start"])
        self.battery = self._config["initial_battery"]
        self.time = self._config["time_budget"]
        self.actions = 0
        self.energy_used = 0
        self.outcome = "searching"
        self._investigated = set()
        self.width = len(self._config["grid"][0])
        self.height = len(self._config["grid"])

    def public_briefing(self):
        return copy.deepcopy(briefing(self._config))

    def _terrain(self, cell):
        return self._config["grid"][cell[1]][cell[0]]

    def observation(self):
        visible = [self.position] + neighbors(self.position, self.width, self.height)
        terrain = [{"cell": list(c), "kind": self._terrain(c)} for c in visible]
        clues = [c for c in self._config["clues"] if tuple(c) in visible and tuple(c) not in self._investigated]
        contact = self.position == tuple(self._config["eve"])
        if contact:
            self.outcome = "found"
        return {"position": list(self.position), "battery": self.battery, "time_remaining": self.time,
                "actions": self.actions, "terrain": terrain, "clues": copy.deepcopy(clues),
                "contact": {"location": list(self.position), "status": self._config["eve_status"]} if contact else None,
                "outcome": self.outcome}

    def _signal(self, outlier_rate):
        maximum = self.width+self.height-2
        actual = distance(self.position, self._config["eve"])
        if self._rng.random() < outlier_rate:
            measured = self._rng.randint(0, maximum)
        else:
            error = self._rng.choices([-1, 0, 1], weights=[.2, .6, .2])[0]
            measured = max(0, min(maximum, actual+error))
        return {"origin": list(self.position), "range": measured, "outlier_rate": outlier_rate,
                "strength": round(1-measured/maximum, 4),
                "timestamp": self._config["mission_time"] + self._config["time_budget"]-self.time}

    def step(self, action):
        if self.outcome != "searching":
            return {**self.observation(), "error": "Mission has ended"}
        kind = action.get("kind")
        error = None
        target = action.get("to")
        if kind not in self._config["action_costs"]:
            error = "Unknown action"
        elif kind == "move" and (not isinstance(target, (list, tuple)) or tuple(target) not in neighbors(self.position, self.width, self.height) or self._terrain(target) == "#"):
            error = "Movement requires an adjacent traversable cell"
        elif kind == "investigate" and (list(self.position) not in self._config["clues"] or self.position in self._investigated):
            error = "No unexamined clue here"
        elif kind == "recharge" and self._terrain(self.position) != "C":
            error = "No charging station here"
        if error:
            return {**self.observation(), "error": error}
        energy, duration = self._config["action_costs"][kind]
        if self.battery < energy or self.time < duration:
            self.outcome = "resource_exhausted"
            return {**self.observation(), "error": "Insufficient resources"}
        self.battery -= energy
        self.time -= duration
        self.energy_used += energy
        self.actions += 1
        extras = {}
        if kind == "move":
            self.position = tuple(target)
        elif kind == "scan":
            extras["signal"] = self._signal(self._config["sensor"]["outlier_rate"])
        elif kind == "investigate":
            self._investigated.add(self.position)
            statuses = ["ready", "stranded", "damaged"]
            actual = self._config["eve_status"]
            report = self._rng.choices(statuses, weights=[.8 if s == actual else .1 for s in statuses])[0]
            extras["evidence"] = {"cell": list(self.position), "signal": self._signal(.04), "status_hint": report, "status_reliability": .8}
        elif kind == "recharge":
            self.battery = self._config["battery_capacity"]
        elif kind == "end":
            self.outcome = "returned" if self.position == tuple(self._config["start"]) or self._terrain(self.position) == "C" else "stopped"
        if self.outcome == "searching" and self.actions >= self._config["max_actions"]:
            self.outcome = "action_limit"
        if self.outcome == "searching" and self.time <= 0:
            self.outcome = "time_limit"
        return {**self.observation(), **extras}

    def evaluator_truth(self):
        """For post-run scoring only. Runner never gives this to Agent."""
        return {"eve": self._config["eve"], "status": self._config["eve_status"]}
