"""Known-map A* and inspectable search/safety decisions."""
import heapq
from .belief import Belief
from .config import distance, neighbors


def astar(known, start, goal, width, height):
    """Return route excluding start; unknown cells are never traversed."""
    queue = [(distance(start, goal), 0, start)]
    costs, parent = {start: 0}, {}
    while queue:
        _, cost, cell = heapq.heappop(queue)
        if cell == goal:
            route = []
            while cell != start:
                route.append(cell)
                cell = parent[cell]
            return list(reversed(route))
        if cost != costs[cell]:
            continue
        for nxt in neighbors(cell, width, height):
            if known.get(nxt) not in (".", "C"):
                continue
            new = cost+1
            if new < costs.get(nxt, float("inf")):
                costs[nxt], parent[nxt] = new, cell
                heapq.heappush(queue, (new+distance(nxt, goal), new, nxt))
    return None


class Agent:
    def __init__(self, info, baseline=False):
        self.info = info
        self.baseline = baseline
        self.belief = Belief(info)
        self.known = {}
        self.visited = set()
        self.clues = set()
        self.investigated = set()
        self.scans = {}
        self.position = tuple(info["start"])
        self.obs = None
        self.target = None
        self.returning = False
        self.last_summary = None

    def observe(self, obs):
        self.obs = obs
        self.position = tuple(obs["position"])
        self.visited.add(self.position)
        for tile in obs["terrain"]:
            self.known[tuple(tile["cell"])] = tile["kind"]
        self.clues.update(tuple(c) for c in obs["clues"])
        if obs.get("evidence"):
            self.investigated.add(tuple(obs["evidence"]["cell"]))
        if obs.get("signal"):
            self.scans[self.position] = self.scans.get(self.position, 0)+1
        self.belief.observe(obs)

    def route(self, start, end):
        return astar(self.known, start, end, self.info["width"], self.info["height"])

    def safety_route(self, cell):
        safe = {tuple(self.info["start"])} | {c for c, kind in self.known.items() if kind == "C"}
        routes = [(self.route(cell, c), c) for c in sorted(safe)]
        choices = [(r, c) for r, c in routes if r is not None]
        return min(choices, key=lambda pair: (len(pair[0]), pair[1])) if choices else (None, None)

    def decide(self):
        obs, costs = self.obs, self.info["action_costs"]
        current = self.belief.summary()
        back, safe = self.safety_route(self.position)
        back_length = len(back) if back is not None else float("inf")
        reserve = back_length*costs["move"][0]
        duration = back_length*costs["move"][1]
        battery, time = obs["battery"], obs["time_remaining"]
        margin = costs["move"][0]*2 + costs["scan"][0]

        def decision(kind, reason, target=None, **details):
            previous = self.target
            self.target = target
            result = {"action": {"kind": kind}, "objective": reason,
                      "target": list(target) if target is not None else None,
                      "previous_target": list(previous) if previous is not None else None,
                      "target_changed": previous is not None and previous != target,
                      "belief": current, "return_energy": reserve,
                      "battery": battery, "time_remaining": time, **details}
            if kind == "move":
                result["action"]["to"] = list(self.route(self.position, target)[0])
            self.last_summary = result
            return result

        if obs["outcome"] != "searching":
            return decision("end", "Mission has already ended")
        if back is None:
            return decision("end", "No known route to safety")
        if time < duration+2*costs["move"][1] or battery < reserve+margin:
            self.returning = True
        if self.returning:
            # Prefer a reachable charger over the start if both are safe to reach.
            chargers = []
            for c, kind in self.known.items():
                if kind != "C":
                    continue
                route = self.route(self.position, c)
                if route is not None and len(route)*costs["move"][0] <= battery and len(route)*costs["move"][1]+costs["recharge"][1]+4*costs["move"][1] < time:
                    chargers.append((len(route), c, route))
            if chargers:
                _, safe, back = min(chargers)
            if back:
                if len(back)*costs["move"][0] > battery or len(back)*costs["move"][1] > time:
                    return decision("end", "Cannot afford return; stop and request recovery")
                return decision("move", "Return to safety before spending the remaining reserve", safe)
            if (self.known[self.position] == "C" and battery < self.info["battery_capacity"] and
                    time > costs["recharge"][1]+4*costs["move"][1] and self.info["battery_capacity"] >= margin):
                self.returning = False
                return decision("recharge", "Recharge at the discovered station before another search")
            return decision("end", "Search budget is too small for a safe excursion", self.position)

        def affordable(kind):
            energy, seconds = costs[kind]
            return battery >= reserve+energy and time >= duration+seconds

        if self.position in self.clues-self.investigated and affordable("investigate"):
            return decision("investigate", "Inspect a discovered clue: more reliable range and status evidence", self.position)
        if not self.baseline and self.scans.get(self.position, 0) == 0 and affordable("scan"):
            # Spatially separate readings, reducing energy use while triangulating.
            recent = list(self.scans)
            if not recent or min(distance(self.position, c) for c in recent) >= 3:
                return decision("scan", "Take a range reading from a new observation position", self.position)

        candidates = []
        for cell, terrain in self.known.items():
            if terrain == "#" or cell == self.position:
                continue
            unseen = [n for n in neighbors(cell, self.info["width"], self.info["height"]) if n not in self.known]
            clue = cell in self.clues-self.investigated
            if cell in self.visited and not unseen and not clue:
                continue
            route = self.route(self.position, cell)
            home, _ = self.safety_route(cell)
            if route is None or home is None:
                continue
            length = len(route)
            required_energy = (length+len(home))*costs["move"][0]
            required_time = (length+len(home))*costs["move"][1]
            if required_energy > battery or required_time > time:
                continue
            mass = sum(p/(1+distance(cell, h))**2 for h, p in self.belief.probabilities.items())
            novelty = len(unseen)/4
            score = 6*mass + .55*novelty + .65*clue + .12*(cell not in self.visited) - .035*length
            if self.baseline:
                score = -length + .01*novelty  # Nearest unvisited/frontier, no beliefs.
            candidates.append((score, cell, length, required_energy, mass, novelty))
        if candidates:
            score, target, length, required_energy, mass, novelty = max(candidates, key=lambda v: (v[0], -v[1][1], -v[1][0]))
            return decision("move", "Explore the nearest frontier" if self.baseline else "Search where belief, new terrain and clues justify the travel cost", target,
                            score=score, belief_mass=mass, novelty=novelty, travel_steps=length, required_energy=required_energy)
        # No affordable search target. A recharge may make a farther target viable.
        if self.known[self.position] == "C" and battery < self.info["battery_capacity"] and affordable("recharge") and time > costs["recharge"][1]+4*costs["move"][1]:
            return decision("recharge", "Refill: no remaining search target fits the current charge")
        if back:
            self.returning = True
            return decision("move", "No safe search target remains; return", safe)
        return decision("end", "No reachable search target fits the remaining budget", self.position)
