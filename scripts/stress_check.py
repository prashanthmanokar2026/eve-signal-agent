"""Exercise changed action costs, partial charges, and maps without chargers."""
import random
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from echo.config import generate
from echo.runner import Mission

for seed in range(1000, 1050):
    rng = random.Random(seed)
    config = generate(seed)
    config['battery_capacity'] = rng.randint(3, 30)
    config['initial_battery'] = rng.randint(0, config['battery_capacity'])
    config['time_budget'] = rng.randint(5, 70)
    config['action_costs'] = {
        'move': [rng.randint(1, 3), rng.randint(1, 4)],
        'scan': [rng.randint(0, 5), rng.randint(1, 4)],
        'investigate': [rng.randint(0, 5), rng.randint(1, 4)],
        'recharge': [0, rng.randint(1, 10)], 'end': [0, 0]
    }
    if seed % 2:
        config['grid'] = [row.replace('C', '.') for row in config['grid']]
    mission = Mission(config)
    for _ in range(250):
        if mission.env.outcome != 'searching':
            break
        mission.step()
        assert 'error' not in mission.trace[-1]['observation'], (seed, mission.trace[-1])
        assert mission.env.battery >= 0 and mission.env.time >= 0
    else:
        raise AssertionError(('Nonterminating mission', seed))
print('50 varied-cost/budget stress runs passed.')
