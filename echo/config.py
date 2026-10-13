"""Validate trusted simulator input; construct a separate public agent briefing."""
import json
import math
import random
from pathlib import Path

DEFAULT_COSTS = {"move": [1, 1], "scan": [2, 1], "investigate": [1, 1], "recharge": [0, 3], "end": [0, 0]}


def neighbors(cell, width, height):
    x, y = cell
    return [(a, b) for a, b in ((x+1, y), (x, y+1), (x-1, y), (x, y-1))
            if 0 <= a < width and 0 <= b < height]


def distance(a, b):
    return abs(a[0]-b[0]) + abs(a[1]-b[1])


def number(value, name, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(name + " must be a finite number >= " + str(minimum))
    return value


def generate(seed, width=12, height=9):
    rng = random.Random(seed)
    grid = [["#" if rng.random() < .17 else "." for _ in range(width)] for _ in range(height)]
    grid[0][0] = "C"
    reachable = {(0, 0)}
    queue = [(0, 0)]
    for cell in queue:
        for nxt in neighbors(cell, width, height):
            if grid[nxt[1]][nxt[0]] != "#" and nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    if len(reachable) < width*height//2:
        return generate(seed+10000, width, height)
    far = sorted(c for c in reachable if distance(c, (0, 0)) >= (width+height)//2)
    eve = rng.choice(far or sorted(reachable-{(0, 0)}))
    candidates = sorted(reachable-{(0, 0), eve})
    charger = rng.choice(candidates)
    grid[charger[1]][charger[0]] = "C"
    return {"name": "Seed " + str(seed), "seed": seed, "grid": ["".join(row) for row in grid],
            "start": [0, 0], "eve": list(eve), "eve_status": rng.choice(["ready", "stranded", "damaged"]),
            "clues": [list(c) for c in rng.sample(candidates, min(6, len(candidates)))],
            "battery_capacity": 36, "time_budget": 160, "max_actions": 180,
            "sensor": {"outlier_rate": .22}, "action_costs": DEFAULT_COSTS}


def validate(raw):
    if not isinstance(raw, dict):
        raise ValueError("Mission must be a JSON object")
    cfg = dict(raw)
    seed = cfg.get("seed", 0)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    if "grid" not in cfg:
        cfg = {**generate(seed), **cfg}
    grid = cfg["grid"]
    if (not isinstance(grid, list) or not 2 <= len(grid) <= 30 or
            not all(isinstance(row, str) for row in grid) or not 2 <= len(grid[0]) <= 30 or
            any(len(row) != len(grid[0]) or set(row)-set(".#C") for row in grid)):
        raise ValueError("grid must be rectangular (2–30 per side), using ., # and C")
    width, height = len(grid[0]), len(grid)
    def coord(value, label):
        if (not isinstance(value, (list, tuple)) or len(value) != 2 or
                any(isinstance(v, bool) or not isinstance(v, int) for v in value) or
                not 0 <= value[0] < width or not 0 <= value[1] < height or grid[value[1]][value[0]] == "#"):
            raise ValueError(label + " must be a traversable [x, y] coordinate")
        return list(value)
    cfg["start"] = coord(cfg.get("start", [0, 0]), "start")
    cfg["eve"] = coord(cfg.get("eve"), "eve")
    clues = cfg.get("clues", [])
    if not isinstance(clues, list):
        raise ValueError("clues must be a list")
    cfg["clues"] = [coord(c, "clue") for c in clues]
    if len({tuple(c) for c in cfg["clues"]}) != len(clues):
        raise ValueError("clues must be unique")
    cfg["eve_status"] = cfg.get("eve_status", "stranded")
    if cfg["eve_status"] not in ("ready", "stranded", "damaged"):
        raise ValueError("Invalid eve_status")
    cfg["battery_capacity"] = number(cfg.get("battery_capacity", 36), "battery_capacity", .01)
    cfg["initial_battery"] = number(cfg.get("initial_battery", cfg["battery_capacity"]), "initial_battery")
    if cfg["initial_battery"] > cfg["battery_capacity"]:
        raise ValueError("initial_battery exceeds capacity")
    cfg["time_budget"] = number(cfg.get("time_budget", 140), "time_budget", .01)
    cfg["max_actions"] = cfg.get("max_actions", 180)
    if isinstance(cfg["max_actions"], bool) or not isinstance(cfg["max_actions"], int) or not 1 <= cfg["max_actions"] <= 2000:
        raise ValueError("max_actions must be an integer from 1 to 2000")
    costs = cfg.get("action_costs", {})
    if not isinstance(costs, dict) or set(costs)-set(DEFAULT_COSTS):
        raise ValueError("Unknown action cost")
    cfg["action_costs"] = {**DEFAULT_COSTS, **costs}
    for action, cost in cfg["action_costs"].items():
        if not isinstance(cost, (list, tuple)) or len(cost) != 2:
            raise ValueError("Costs are [battery, time]")
        number(cost[0], action+" energy")
        number(cost[1], action+" time", 0 if action == "end" else .01)
    if cfg["action_costs"]["move"][0] <= 0 or cfg["action_costs"]["recharge"][0] != 0 or cfg["action_costs"]["end"] != [0, 0]:
        raise ValueError("Move must cost energy; recharge energy and end costs must be zero")
    sensor = cfg.get("sensor", {})
    if not isinstance(sensor, dict):
        raise ValueError("sensor must be an object")
    rate = number(sensor.get("outlier_rate", .2), "outlier_rate")
    if rate > 1:
        raise ValueError("outlier_rate must be <= 1")
    cfg["sensor"] = {"outlier_rate": rate}
    initial = cfg.get("initial_signal")
    if initial is not None:
        if not isinstance(initial, dict):
            raise ValueError("initial_signal must be an object")
        number(initial.get("timestamp"), "initial_signal timestamp")
        if number(initial.get("strength"), "initial_signal strength") > 1:
            raise ValueError("strength must be <= 1")
        if "coordinates" in initial:
            c = initial["coordinates"]
            if not isinstance(c, list) or len(c) != 2:
                raise ValueError("signal coordinates must be [x,y]")
            for i, bound in zip(c, [width, height]):
                if number(i, "signal coordinate") >= bound:
                    raise ValueError("signal coordinate outside grid")
        elif initial.get("direction") not in ["N", "E", "S", "W"]:
            raise ValueError("initial_signal needs coordinates or N/E/S/W direction")
    cfg["mission_time"] = number(cfg.get("mission_time", 0), "mission_time")
    if initial and initial["timestamp"] > cfg["mission_time"]:
        raise ValueError("initial signal cannot be from the future")
    cfg["name"] = str(cfg.get("name", "Untitled mission"))[:100]
    cfg["seed"] = seed
    return cfg


def load(path):
    try:
        return validate(json.loads(Path(path).read_text()))
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid mission configuration: " + str(exc)) from exc


def briefing(cfg):
    """An allowlist: never pass cfg, grid, clues, seed, or EVE to the planner."""
    return {"width": len(cfg["grid"][0]), "height": len(cfg["grid"]),
            **{key: cfg[key] for key in ("name", "start", "battery_capacity", "time_budget", "action_costs", "sensor", "mission_time")},
            "initial_signal": cfg.get("initial_signal")}
