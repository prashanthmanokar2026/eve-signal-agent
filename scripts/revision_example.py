"""Export a counterfactual test: same world/resources, with and without one clue."""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from echo.config import load
from echo.runner import Mission


def main():
    root=Path(__file__).resolve().parent.parent
    mission=Mission(load(root/'missions/false-echo.json'))
    initial=mission.agent.belief.summary()
    for _ in range(6):mission.step()
    without=copy.deepcopy(mission.agent)
    before=without.belief.summary()
    last_target=mission.trace[-1]['decision']['target']
    mission.step()
    observation=mission.trace[-1]['observation']
    # Retain identical movement, discovered map, resources and clue-consumption state.
    # Remove only this clue's range/status evidence from the counterfactual update.
    without.observe({k:v for k,v in observation.items() if k!='evidence'})
    without.investigated.add(tuple(observation['evidence']['cell']))
    actual=mission.agent.decide();counterfactual=without.decide()
    result={'initial_belief':initial,'initial_movement_target':mission.trace[1]['decision']['target'],
            'step':7,'target_before_clue':last_target,'belief_before':before,'new_observation':observation['evidence'],
            'belief_after':mission.agent.belief.summary(),'next_decision':actual,'without_clue_decision':counterfactual,
            'interpretation':'Holding map, resources and clue consumption fixed, the new evidence changes the next movement target.'}
    target=root/'results/false-echo/revision.json';target.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved',target.relative_to(root))


if __name__=='__main__':main()
