"""Check saved candidate provenance and summarize tool failures without model calls."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


IMPLEMENTATION_FILES = {'benchmark_solver.py', 'prepared_workspace.py', 'model.py', 'benchmark_inputs.py'}


def audit_candidate(directory: Path):
    def read(name):
        return json.loads((directory/name).read_text())
    manifest, result, task = read('manifest.json'), read('result.json'), read('task.json')
    instance = task['instance_id']
    if manifest['instance_id'] != instance or result['instance_id'] != instance:
        raise ValueError('Instance identity mismatch')
    if result['status'] not in ('finished', 'budget_exhausted'):
        raise ValueError('Candidate run did not finish normally; preserve its infrastructure error separately')
    expected_implementation = IMPLEMENTATION_FILES | ({'repository_policy.py'} if isinstance(manifest.get('policy'), dict) else set())
    if set(manifest['implementation']) != expected_implementation:
        raise ValueError('Unexpected implementation snapshot set')
    for name, digest in manifest['implementation'].items():
        if hashlib.sha256((directory/'implementation'/name).read_bytes()).hexdigest() != digest:
            raise ValueError('Implementation snapshot hash mismatch')
    prediction_lines = (directory/'prediction.jsonl').read_text().splitlines()
    if len(prediction_lines) != 1:
        raise ValueError('Expected exactly one prediction')
    prediction = json.loads(prediction_lines[0])
    patch = (directory/'patch.diff').read_bytes().decode('utf-8')
    if prediction['instance_id'] != instance or prediction['model_patch'] != patch:
        raise ValueError('Prediction differs from saved patch/instance')
    if len(patch.encode()) != result['patch_bytes']:
        raise ValueError('Patch size differs from result')
    calls = sorted((directory/'model_calls').glob('step-*.json'))
    steps = sorted(directory.glob('step-*.json'))
    if not 1 <= len(calls) == len(steps) <= manifest['steps']:
        raise ValueError('Model call / step count mismatch')
    usage = {'calls': len(calls), 'input_tokens': 0, 'output_tokens': 0, 'request_seconds': 0, 'errors': 0}
    actions, failed_actions = Counter(), Counter()
    last_action = None
    for index, (call_path, step_path) in enumerate(zip(calls, steps)):
        expected = f'step-{index:03d}.json'
        if call_path.name != expected or step_path.name != expected:
            raise ValueError('Noncontiguous call or step logs')
        call, step = json.loads(call_path.read_text()), json.loads(step_path.read_text())
        if call['role'] != 'discovery' or call['id'] != expected[:-5]:
            raise ValueError('Call identity mismatch')
        if call['request']['model'] != prediction['model_name_or_path']:
            raise ValueError('Prediction model differs from request')
        if call['request']['options']['seed'] != manifest['seed'] + index:
            raise ValueError('Request seed differs from registered sequence')
        if call['request']['options']['num_predict'] != manifest['max_tokens_per_call']:
            raise ValueError('Output budget differs from registered budget')
        response = call.get('response', {})
        if not call.get('error'):
            if json.loads(response['message']['content']) != step['action']:
                raise ValueError('Recorded action differs from model output')
        elif step['action'] is not None:
            raise ValueError('Failed model call unexpectedly supplied an action')
        usage['input_tokens'] += response.get('prompt_eval_count', 0)
        usage['output_tokens'] += response.get('eval_count', 0)
        usage['request_seconds'] += call['wall_seconds']
        usage['errors'] += int('error' in call)
        action = step['action'] or {}
        last_action = action.get('action', 'invalid')
        actions[last_action] += 1
        observation = step['observation']
        if observation.get('returncode', 0) != 0 or 'invalid_action' in observation:
            failed_actions[json.dumps(action, sort_keys=True)] += 1
    if usage != result['usage']['discovery']:
        raise ValueError('Reported model usage differs from raw call logs')
    if result['status'] == 'finished' and last_action != 'finish':
        raise ValueError('Finished result lacks a finish action')
    if result['status'] == 'budget_exhausted' and len(calls) != manifest['steps']:
        raise ValueError('Budget exhaustion reported before call budget was consumed')
    return {'instance_id': instance, 'status': result['status'], 'usage': usage,
            'patch_bytes': len(patch.encode()), 'patch_sha256': hashlib.sha256(patch.encode()).hexdigest(),
            'actions': dict(actions), 'failed_tool_actions': sum(failed_actions.values()),
            'most_repeated_failed_action_count': max(failed_actions.values(), default=0),
            'scope': 'Saved-record consistency only; not patch execution or official resolution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_candidate(args.run), indent=2))


if __name__ == '__main__':
    main()
