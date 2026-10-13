# Experiments

## Question and setup

Does using noisy range evidence and belief-weighted exploration improve contact success over a simple systematic search with the same resource limits?

Run from the repository root:

```sh
python3 -m echo evaluate --count 30 --seed 100 --output results/benchmark
```

This evaluates **30 generated worlds, seeds 100–129**, once with each policy. Maps are 12×9, with approximately 17% obstacles before connectivity checks, start `(0,0)`, two charging stations, six hidden clues, battery capacity 36, time budget 160, action cap 180 and normal-scan outlier rate 0.22. EVE and clues are placed in the start's connected component. Worlds with a very small connected component are regenerated deterministically. EVE is placed relatively far from the start.

These generated missions have no hand-supplied directional or coordinate hint. They are separate from the three presentation scenarios. The results below were produced by the checked-in implementation; raw per-seed rows are in [`runs.csv`](results/benchmark/runs.csv). No failed runs were removed.

## Baseline and fairness

The baseline chooses the nearest unvisited/frontier target. It receives the same public briefing, local visibility, signal model, action menu, discovered clues and resource costs. It uses the same return/recharge safeguards and investigates clues. It maintains the same belief filter for final reporting, but its target selection ignores that belief and it does not choose normal scans.

Each pair starts with identical truth and sensor seed. Because the policies take different action sequences, they consume random draws differently; this is paired-world evaluation, **not** a common observation tape. The comparison measures the whole policies, including scan costs. A matched-scan baseline and separate ablations would be needed to isolate Bayesian inference or target scoring alone.

## Actual results

| Metric | ECHO | Systematic baseline |
|---|---:|---:|
| Contact success | 27/30 (90.0%) | 20/30 (66.7%) |
| Mean executed actions | 64.2 | 105.9 |
| Mean total energy consumed | 69.6 | 102.87 |
| Mean normal scans | 7.0 | 0.0 |
| Mean final localization error, cells | 0.0 | 0.067 |
| Outcome: found | 27 | 20 |
| Outcome: returned without contact | 1 | 9 |
| Outcome: time limit | 2 | 1 |

![Success chart](results/benchmark/success.svg)

**Success** requires direct contact at EVE's cell. **Localization error** is Manhattan distance between the final highest-probability cell and true EVE, measured only by the evaluator after the run. Zero error does not imply contact: ECHO's three unsuccessful runs inferred the right cell but did not reach it within the budget. The planner never receives the evaluator's truth.

Actions include recharges and explicit endings. Energy is total expenditure, not battery remaining; recharging allows it to exceed capacity. Scans exclude clue investigations. Means include unsuccessful runs, whose effort is often larger, so they are not “cost per successful search.”

## Mixed outcomes

- ECHO alone made contact on seeds **100, 101, 102, 108, 116, 123, 125, 128**.
- The baseline alone made contact on seed **119**.
- Both failed to make contact on **110 and 115**.
- The baseline used fewer actions on **3** of the **19** worlds where both made contact.

The result supports a useful improvement on this particular generator, not universal superiority. A simple traversal can get lucky; a cautious evidence-driven policy can spend resources on measurements or return early.

## Demonstration missions

| Mission | Seed | Actions | Energy | Outcome |
|---|---:|---:|---:|---|
| First Contact | 7 | 22 | 26 | Found, stranded |
| False Echo | 19 | 44 | 47 | Found, damaged |
| The Last Charge | 11 | 44 | 46 | Found, ready |

False Echo's action-7 counterfactual is saved in [`revision.json`](results/false-echo/revision.json) and regenerated with `python3 scripts/revision_example.py`. Without that clue's new evidence, the next target is `[5,0]`; with it, the next target is `[4,1]`. The Last Charge starts with 8/20 battery and recharges at actions **6, 22 and 39**. The traces contain each resource deduction and observation.

## Verification and limits

The automated suite covers validation, legal/illegal transitions, sensor likelihood normalization, Bayesian arithmetic, strong/contradictory noise, A*, hidden-state boundaries, deterministic replay, mission exports, baseline evaluation, concurrent requests and reset isolation. All 49 tests passed locally and in GitHub Actions on Python 3.9, 3.12 and 3.13. Run them with `python3 -m unittest discover -s tests -v`.

Thirty small synthetic worlds give limited statistical precision. The generator excludes unreachable EVE for these benchmark runs, although disconnected missions are tested separately. The inference model matches the simulator's model, making this easier than real-world sensing. No confidence calibration study, statistical significance claim, learned policy, moving target, wall-dependent radio attenuation or persistent spoof transmitter was evaluated.
