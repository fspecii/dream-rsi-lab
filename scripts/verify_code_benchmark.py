"""Reexecute a saved coding benchmark with Docker, without model inference."""
import argparse
import hashlib
import json
from pathlib import Path

from dream_rsi.code_benchmark import summarize
from dream_rsi.code_workflow import assess_selected
from dream_rsi.engine import replay
from dream_rsi.policy import Policy, PolicySpec
from dream_rsi.sandbox import DockerSandbox
from dream_rsi.tasks.coding import CodingTask, validate_suite
from dream_rsi.types import World


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify(directory):
    def read(path):
        return json.loads((directory / path).read_text())
    manifest, result = read('manifest.json'), read('result.json')
    suite = validate_suite(read('suite.json'))
    digest = hashlib.sha256(json.dumps(suite, sort_keys=True).encode()).hexdigest()
    check(digest == manifest['suite_digest'], 'Suite digest mismatch')
    sandbox = DockerSandbox(image=manifest['runtime']['image'])
    check(sandbox.inspect() == manifest['runtime'], 'Recorded Docker image is unavailable')
    check(len(result['pairs']) == len(manifest['plan']), 'Incomplete benchmark')
    total_nodes = 0
    for planned, pair in zip(manifest['plan'], result['pairs']):
        check(all(pair[k] == v for k, v in planned.items()), 'Pair differs from registered plan')
        task = CodingTask(suite, 'test', sandbox, pair['problem'])
        case = task.case(pair['seed'])
        for arm in ('fixed', 'candidate'):
            row = pair[arm]
            world = World.from_dict(read('worlds/' + row['world'] + '/world.json'))
            check(world.seed == pair['seed'] and world.case_id == pair['problem'], 'World identity mismatch')
            check(world.task_input == case.input and world.task_private == case.private, 'World tests changed')
            check(world.baseline_artifact == case.baseline, 'Baseline source changed')
            baseline = task.evaluate_artifact(case.baseline, case)
            check(baseline.score == world.baseline_score, 'Baseline score does not reproduce')
            for node in world.nodes:
                raw = read('model_calls/' + node.model_call_id + '.json')
                if node.artifact:
                    proposed = json.loads(raw['response']['message']['content'])['source']
                    check(proposed == node.artifact == node.source, 'Source differs from model output')
                else:
                    check('error' in raw or not node.evaluation.valid, 'Missing source without recorded failure')
                measured = task.evaluate_artifact(node.artifact, case)
                check((measured.score, measured.valid) == (node.evaluation.score, node.evaluation.valid),
                      'Visible evaluation does not reproduce: ' + node.id)
            spec = PolicySpec(**manifest['champion']['policy']) if arm == 'candidate' else PolicySpec()
            check(world.policy == spec.to_dict(), 'Wrong controller')
            episode = replay(Policy(spec), world, manifest['config']['branches'] * manifest['config']['depth'])
            check(episode.decisions == world.decisions, 'Online decisions differ from replay')
            actual = assess_selected(task, world)
            saved = read('assessments/' + row['world'] + '.json')
            for key in ('source', 'node', 'visible_score', 'hidden_score', 'hidden_valid'):
                check(actual[key] == saved[key], 'Selected assessment does not reproduce: ' + key)
            check(row['private_score'] == actual['hidden_score'] and row['visible_score'] == actual['visible_score'], 'Pair score mismatch')
            check(row['calls'] == len(world.nodes), 'Call count mismatch')
            check(row['solved'] == (actual['hidden_valid'] and actual['hidden_score'] == 1), 'Solved flag mismatch')
            total_nodes += len(world.nodes)
    expected = {**summarize(result['pairs']), 'policy_changed': manifest['champion']['policy'] != PolicySpec().to_dict()}
    check(result['summary'] == expected, 'Headline summary mismatch')
    print(f"Verified {len(result['pairs'])} pairs and {total_nodes} generated programs against the recorded Docker image; no model calls.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    verify(parser.parse_args().directory.resolve())
