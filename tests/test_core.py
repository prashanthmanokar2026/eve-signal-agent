import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from echo.belief import Belief, range_likelihood
from echo.config import DEFAULT_COSTS, briefing, generate, load, validate
from echo.environment import Environment
from echo.planner import Agent, astar
from echo.runner import Mission
from echo.evaluate import evaluate

ROOT = Path(__file__).resolve().parent.parent


def tiny(**changes):
    return {"name": "Test", "seed": 2, "grid": ["C...", ".#..", "...."], "start": [0, 0],
            "eve": [3, 2], "clues": [[1, 0]], "battery_capacity": 20, "time_budget": 40, **changes}


class ConfigurationTests(unittest.TestCase):
    def test_samples_load(self):
        for path in (ROOT/"missions").glob("*.json"):
            self.assertEqual(load(path)["name"], json.loads(path.read_text())["name"])

    def test_generated_config_reproducible(self):
        self.assertEqual(validate({"seed": 9}), validate({"seed": 9}))

    def test_invalid_grid(self):
        for grid in [[], ["..", "."], ["??", ".."], "bad", [None, None]]:
            with self.subTest(grid=grid), self.assertRaises(ValueError):
                validate(tiny(grid=grid))

    def test_invalid_positions(self):
        for key, value in [("eve", [1, 1]), ("start", [-1, 0]), ("clues", [[4, 0]]), ("eve", [True, 0])]:
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                validate(tiny(**{key: value}))

    def test_invalid_costs(self):
        for costs in [{"move": [-1, 1]}, {"move": [0, 1]}, {"scan": [1, 0]}, {"scan": [float('nan'), 1]}, {"end": [1, 0]}, {"dance": [1, 1]}, {"scan": 2}]:
            with self.subTest(costs=costs), self.assertRaises(ValueError):
                validate(tiny(action_costs=costs))

    def test_invalid_budgets(self):
        for changes in [{"max_actions": 0}, {"time_budget": -1}, {"initial_battery": 21}, {"battery_capacity": float('inf')}, {"seed": False}, {"max_actions": 1.2}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate(tiny(**changes))

    def test_invalid_sensor_and_initial(self):
        for changes in [{"sensor": {"outlier_rate": 1.2}}, {"initial_signal": {"strength": 1, "timestamp": 0, "direction": "Q"}}, {"initial_signal": {"coordinates": [1, 1], "strength": 1, "timestamp": 5}}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate(tiny(**changes))

    def test_missing_chargers_allowed(self):
        cfg = validate(tiny(grid=["....", ".#..", "...."]))
        self.assertNotIn('C', ''.join(cfg['grid']))

    def test_bad_json_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'bad.json';path.write_text('{')
            with self.assertRaises(ValueError):load(path)


class EnvironmentTests(unittest.TestCase):
    def test_legal_movement_and_resource_deduction(self):
        env=Environment(tiny())
        obs=env.step({"kind":"move","to":[1,0]})
        self.assertEqual((obs['position'],obs['battery'],obs['time_remaining']),([1,0],19,39))

    def test_illegal_movement_has_no_side_effect(self):
        env=Environment(tiny());initial=env.observation()
        for target in [[1,1],[-1,0],[3,2],None]:
            self.assertIn('error',env.step({'kind':'move','to':target}))
            self.assertEqual(env.observation(),initial)

    def test_invalid_actions(self):
        env=Environment(tiny())
        self.assertIn('error',env.step({'kind':'dance'}))
        self.assertIn('error',env.step({'kind':'investigate'}))

    def test_scan_cost_and_measurement(self):
        env=Environment(tiny())
        obs=env.step({'kind':'scan'})
        self.assertEqual(obs['battery'],18)
        self.assertEqual(obs['signal']['origin'],[0,0])
        self.assertTrue(0<=obs['signal']['range']<=5)
        self.assertNotIn('actual',obs['signal'])

    def test_investigation_only_at_clue(self):
        env=Environment(tiny());env.step({'kind':'move','to':[1,0]})
        obs=env.step({'kind':'investigate'})
        self.assertEqual(obs['evidence']['signal']['outlier_rate'],.04)
        self.assertIn('error',env.step({'kind':'investigate'}))

    def test_recharge_and_wrong_location(self):
        env=Environment(tiny(initial_battery=4))
        obs=env.step({'kind':'recharge'})
        self.assertEqual((obs['battery'],obs['time_remaining']),(20,37))
        env.step({'kind':'move','to':[1,0]})
        self.assertIn('error',env.step({'kind':'recharge'}))

    def test_insufficient_battery_never_negative(self):
        env=Environment(tiny(initial_battery=0))
        obs=env.step({'kind':'move','to':[1,0]})
        self.assertEqual(obs['outcome'],'resource_exhausted');self.assertEqual(obs['battery'],0)

    def test_direct_contact_status(self):
        env=Environment(tiny(eve=[1,0],eve_status='damaged'))
        obs=env.step({'kind':'move','to':[1,0]})
        self.assertEqual(obs['outcome'],'found');self.assertEqual(obs['contact']['status'],'damaged')

    def test_terminal_step_is_inert(self):
        env=Environment(tiny());env.step({'kind':'end'});before=env.observation()
        self.assertIn('error',env.step({'kind':'scan'}));self.assertEqual(env.observation(),before)

    def test_max_actions_and_time_limit(self):
        self.assertEqual(Environment(tiny(max_actions=1)).step({'kind':'scan'})['outcome'],'action_limit')
        self.assertEqual(Environment(tiny(time_budget=1)).step({'kind':'scan'})['outcome'],'time_limit')

    def test_repeated_scans_are_real_and_cost_resources(self):
        env=Environment(tiny())
        observations=[env.step({'kind':'scan'}) for _ in range(5)]
        self.assertEqual(observations[-1]['battery'],10)
        self.assertEqual(len(set(o['signal']['timestamp'] for o in observations)),5)


class InferenceTests(unittest.TestCase):
    def test_likelihood_is_normalized_including_clipped_edges(self):
        for rate in [0,.2,1]:
            for actual in range(6):
                self.assertAlmostEqual(sum(range_likelihood(z,actual,5,rate) for z in range(6)),1)

    def test_bayes_numerical_example(self):
        belief=Belief(briefing(validate(tiny())))
        a,b=(1,0),(2,0)
        belief.probabilities={a:.6,b:.4}
        belief.update({a:.2,b:.8})
        self.assertAlmostEqual(belief.probabilities[a],.12/.44)
        self.assertAlmostEqual(belief.probabilities[b],.32/.44)

    def test_normalized_and_finite_after_many_conflicts(self):
        mission=Mission(tiny());belief=mission.agent.belief
        for i in range(300):
            obs=copy.deepcopy(mission.initial)
            obs['signal']={'origin':[0,0],'range':0 if i%2 else 5,'outlier_rate':.2}
            belief.observe(obs)
        self.assertAlmostEqual(sum(belief.probabilities.values()),1)
        self.assertTrue(all(math.isfinite(p) and 0<=p<=1 for p in belief.probabilities.values()))
        self.assertEqual(belief.probabilities[(0,0)],0)

    def test_zero_likelihood_recovers_without_unexcluding(self):
        belief=Mission(tiny()).agent.belief
        belief.update({c:0 for c in belief.probabilities})
        self.assertEqual(belief.recoveries,1);self.assertEqual(belief.probabilities[(0,0)],0)

    def test_uniform_noise_has_no_location_information(self):
        mission=Mission(tiny());before=dict(mission.agent.belief.probabilities)
        obs=copy.deepcopy(mission.initial);obs['signal']={'origin':[0,0],'range':5,'outlier_rate':1}
        mission.agent.observe(obs)
        for c,p in before.items():self.assertAlmostEqual(mission.agent.belief.probabilities[c],p)

    def test_status_update(self):
        mission=Mission(tiny());obs=copy.deepcopy(mission.initial)
        obs['evidence']={'cell':[0,0],'status_hint':'damaged'}
        mission.agent.belief.observe(obs)
        self.assertAlmostEqual(mission.agent.belief.status['damaged'],.8)

    def test_old_hint_has_less_influence(self):
        cfg=tiny(initial_signal={'coordinates':[3,2],'timestamp':0,'strength':1})
        fresh=Belief(briefing(validate(cfg)))
        old=Belief(briefing(validate({**cfg,'mission_time':100})))
        self.assertGreater(fresh.probabilities[(3,2)],old.probabilities[(3,2)])


class PlannerTests(unittest.TestCase):
    def test_astar_routes_around_obstacle(self):
        known={(x,y):'.' for y in range(3) for x in range(4)};known[(1,0)]='#'
        route=astar(known,(0,0),(2,0),4,3)
        self.assertEqual(len(route),4);self.assertNotIn((1,0),route)

    def test_astar_unknown_and_unreachable(self):
        self.assertIsNone(astar({(0,0):'.'},(0,0),(1,0),4,3))
        self.assertEqual(astar({(0,0):'.'},(0,0),(0,0),4,3),[])

    def test_hidden_information_allowlist(self):
        env=Environment(tiny());info=env.public_briefing()
        self.assertFalse(set(info)&{'grid','eve','eve_status','clues','seed'})
        agent=Agent(info)
        self.assertFalse(any(isinstance(v,Environment) for v in vars(agent).values()))
        obs=env.observation()
        self.assertNotIn([3,2],[t['cell'] for t in obs['terrain']])
        self.assertIsNone(obs['contact'])

    def test_hidden_world_changes_do_not_change_identical_observation_decision(self):
        first=Mission(tiny())
        other=Mission(tiny(eve=[2,2],clues=[[2,1]],seed=999))
        # Use literally the same observed information; changed truth is unavailable.
        other.agent=Agent(other.env.public_briefing());other.agent.observe(first.initial)
        self.assertEqual(first.agent.decide(),other.agent.decide())

    def test_no_valid_movement_terminates(self):
        mission=Mission(tiny(grid=['C#..','##..','....'], clues=[]))
        self.assertEqual(mission.run()['outcome'],'returned')
        self.assertLessEqual(mission.env.actions,3)

    def test_low_battery_recharges(self):
        mission=Mission(tiny(initial_battery=1))
        self.assertEqual(mission.agent.decide()['action']['kind'],'recharge')

    def test_missing_charger_returns(self):
        mission=Mission(tiny(grid=['....','.#..','....'],initial_battery=2))
        report=mission.run();self.assertEqual(report['outcome'],'returned')
        self.assertGreaterEqual(report['battery_remaining'],0)

    def test_sample_missions_and_reserves(self):
        for path in (ROOT/'missions').glob('*.json'):
            with self.subTest(path=path):
                mission=Mission(load(path));report=mission.run()
                self.assertEqual(report['outcome'],'found')
                for row in mission.trace:
                    self.assertNotIn('error',row['observation'])
                    self.assertGreaterEqual(row['observation']['battery'],0)
                    if row['decision']['action']['kind']=='move' and 'required_energy' in row['decision']:
                        self.assertLessEqual(row['decision']['required_energy'],row['decision']['battery'])

    def test_false_echo_counterfactual_replanning(self):
        mission=Mission(load(ROOT/'missions/false-echo.json'))
        for _ in range(6):mission.step()
        before=copy.deepcopy(mission.agent)
        old_location=before.belief.summary()['location']
        mission.step();observation=mission.trace[-1]['observation']
        stripped={k:v for k,v in observation.items() if k!='evidence'}
        before.observe(stripped);before.investigated.add(tuple(observation['evidence']['cell']))
        self.assertNotEqual(old_location,mission.agent.belief.summary()['location'])
        self.assertEqual(mission.agent.decide()['target'],[4,1])
        self.assertEqual(before.decide()['target'],[5,0])


class IntegrationTests(unittest.TestCase):
    def test_deterministic_replay(self):
        a,b=Mission(load(ROOT/'missions/false-echo.json')),Mission(load(ROOT/'missions/false-echo.json'))
        self.assertEqual(a.run(),b.run());self.assertEqual(a.trace,b.trace)

    def test_export_trace_report_visual(self):
        mission=Mission(tiny());mission.run()
        with tempfile.TemporaryDirectory() as folder:
            mission.export(folder)
            self.assertEqual(json.loads((Path(folder)/'report.json').read_text()),mission.report())
            rows=[json.loads(line) for line in (Path(folder)/'trace.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),mission.env.actions)
            self.assertIn('<svg',(Path(folder)/'path.svg').read_text())
            self.assertTrue((Path(folder)/'report.md').is_file())

    def test_baseline_evaluation(self):
        with tempfile.TemporaryDirectory() as folder:
            results=evaluate(3,folder,100)
            self.assertEqual(set(results),{'echo','baseline'})
            self.assertEqual(results['baseline']['mean_scans'],0)
            self.assertEqual(len((Path(folder)/'runs.csv').read_text().splitlines()),7)

    def test_generated_missions_terminate(self):
        for seed in range(5):
            cfg=generate(seed);cfg['sensor']['outlier_rate']=1
            mission=Mission(cfg);mission.run()
            self.assertLessEqual(mission.env.actions,cfg['max_actions'])
            self.assertGreaterEqual(mission.env.battery,0)


if __name__=='__main__':unittest.main()
