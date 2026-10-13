# Algorithms in ECHO

The agent repeats: **observe → update beliefs → choose a target/action → act**. There is no trained model, scripted route, or language-model call.

## 1. Location belief

`Belief.probabilities` maps every grid coordinate to a number from 0 to 1. Before seeing terrain, EVE could be in any cell. A discovered obstacle has probability zero. Standing on a cell without contact rules out that cell. Unseen obstacles can retain probability until discovered.

An optional external hint forms a **soft prior**. Its reliability is

`r = 0.85 × strength × exp(-age / 20)`.

For coordinate hints, `h(c) = exp(-Manhattan(c, hint)² / 8)`. For a direction, `h` is 1 in the indicated half-plane and 0.1 elsewhere. Starting weights are multiplied by `(1-r) + 8rh(c)` and normalized. This is a designed prior, not a calibrated GPS likelihood. It never rules out the rest of the map. Old hints have less influence.

## 2. Sensor model and Bayesian update

Let `H=c` mean that EVE is at cell `c`. For an observation from `o`, the true synthetic range is `d=|cx-ox|+|cy-oy|`. The maximum range is `M=width+height-2`.

With probability `1-q`, add error `-1`, `0`, or `+1` with probabilities `0.2`, `0.6`, `0.2`, then clip the result to `[0,M]`. With probability `q`, draw a uniformly random integer in `[0,M]`. Consequently:

```text
L(z | c) = (1-q) × Σ P(error=e)·1[clip(d+e)=z] + q/(M+1)
P(c | z) = L(z | c) × P(c) / Σ L(z | h) × P(h)
```

`Environment._signal` samples this distribution. `range_likelihood` evaluates the **same** distribution, including the clipped endpoint probabilities. A scan uses the configured `q`; an investigated clue uses `q=0.04`. Uniform interference keeps unexpected readings possible rather than forcing the belief into the wrong cell.

Example: two hypotheses have probabilities 0.6 and 0.4. The measurement likelihoods are 0.2 and 0.8. Their weights become 0.12 and 0.32, so the posterior is **0.273 and 0.727**. Evidence reverses the preferred hypothesis.

Calculations use log weights and subtract the largest log weight before exponentiation. Non-excluded priors are floored at `1e-300` to allow numerical recovery; this introduces negligible regularization rather than preserving exact numerical zeros. If all likelihoods are impossible, the filter resets uniformly over non-excluded cells and increments a visible recovery counter. It never restores ruled-out cells. If every cell is excluded, it raises an explicit contradiction error. The sample runs needed zero recoveries.

Signals are assumed independent conditional on location; our simulator draws fresh errors. Real correlated errors would make repeated readings overconfident.

## 3. EVE's status

A separate categorical belief tracks `ready`, `stranded`, and `damaged`. It begins uniformly. An investigated clue names the true status with probability 0.8, and either other status with probability 0.1. Bayes' rule updates those three weights. A direct contact confirms both location and status. No status hint means the report says **unknown**.

## 4. Known-map A*

`astar` searches four-neighbor movements with unit edge length. Priority is `path_length + Manhattan_to_goal`. Manhattan distance is admissible and consistent for this movement model: walls can lengthen a route, but cannot shorten it below the straight grid distance.

Only cells observed as `.` or `C` can enter the path. Unknown cells are never assumed safe. The returned route excludes the starting cell; an empty route means already at the goal, and `None` means no known route exists. Since move costs are constant within a mission, shortest distance also minimizes travel energy/time.

## 5. Exploration heuristic

A candidate is a discovered traversable cell that is unvisited, borders unknown terrain, or holds an unexamined clue. It must have an affordable known route there and back to a known safe point.

For each candidate `c`:

```text
mass(c) = Σ P(EVE=h) / (1 + Manhattan(c,h))²
novelty(c) = number of unknown cardinal neighbors / 4
score(c) = 6·mass(c) + 0.55·novelty(c) + 0.65·clue(c)
           + 0.12·unvisited(c) - 0.035·route_length(c)
```

The agent chooses the highest score, with deterministic coordinate tie-breaking, and executes only the first move before observing and scoring again. Coefficients are design choices, not learned parameters. `mass` draws exploration toward likely regions; novelty rewards map discovery; clues offer more reliable evidence; distance discourages long detours.

This is **not expected information gain**. The UI and trace show its actual components. Entropy, `-Σp log₂p`, is recorded as a belief diagnostic, not optimized directly.

ECHO takes at most one normal scan per position. It scans when no previous scan position is within Manhattan distance 3. This is a simple spacing rule to avoid spending the entire battery on nearby measurements. Investigations take priority over normal scans.

## 6. Battery and time

Known safe cells are the starting position and discovered charging stations. Returning to a noncharging start allows the mission to stop; it does not recharge the robot.

A candidate requires:

```text
energy >= (route_to_candidate + shortest_known_return_route) × move_energy
time   >= (route_to_candidate + shortest_known_return_route) × move_time
```

For scanning/investigation, the cost must fit **in addition to** the current return reserve. Every observation triggers a fresh decision. Low battery (`return reserve + two moves + one scan`) or low time (`return time + two moves`) enters a return mode. Once returning, the agent follows a feasible known charger if enough time remains for recharging and another excursion; otherwise it returns to the nearest safe point. Return mode avoids switching back to exploration halfway home.

Recharge restores capacity and consumes its configured time. Capacity, elapsed time and action limits prevent unlimited searches. A route can still be impossible with the available capacity, and no policy promises to find EVE. Static obstacles and known-map routing make the return estimate valid for this simulator; changing terrain would require stronger safeguards.

## 7. Replanning and proof

No scenario name, EVE coordinate or hidden clue list appears in the decision calculation. The public `name` is presentation metadata only. The planner rescans targets after each observation; it does not blindly follow a precomputed route.

In False Echo, the action-7 clue changes the MAP estimate from `[8,1]` to `[2,6]`. `scripts/revision_example.py` compares two copies with identical discovered terrain, resources and consumed-clue state. One receives the new measurement; one does not. Their next targets are `[4,1]` and `[5,0]` respectively. The integration test asserts that contrast. Both choices come from the same scoring function.

## 8. Baseline and complexity

The baseline chooses the nearest unvisited/frontier candidate (`-distance + 0.01·novelty`), does not scan, and shares investigation and resource safety logic. It still updates beliefs for reporting, but does not use them in target selection.

For these small maps, clarity matters more than optimization. Each decision computes A* routes for candidates and known safe points. A* is approximately `O(V log V)` on a grid; repeated calls increase total planning work. The belief update is `O(V)`. This implementation is suitable for small demonstrations, not large real-time maps.
