"""Apply the registered exploratory gate; never promote a policy automatically."""
from __future__ import annotations

import hashlib
import json
import argparse
from pathlib import Path

from .benchmark_audit import audit_candidate


def decide(expected, pairs):
    """Pure gate over checked per-instance outcomes, keeping every selected task."""
    if not expected or len(set(expected)) != len(expected):
        raise ValueError('Expected a nonempty unique validation set')
    if len({pair['instance_id'] for pair in pairs}) != len(pairs):
        raise ValueError('Duplicate comparison instance')
    if set(pair['instance_id'] for pair in pairs) - set(expected):
        raise ValueError('Unexpected comparison instance')
    present = {pair['instance_id']: pair for pair in pairs}
    missing = [instance for instance in expected if instance not in present]
    incomplete = [pair['instance_id'] for pair in pairs
                  if any(pair[side].get('status') != 'complete' for side in ('baseline', 'candidate'))]
    if missing or incomplete:
        return {'decision': 'incomplete', 'missing': missing, 'incomplete': incomplete,
                'promoted': False, 'selected_instances': len(expected)}
    for pair in pairs:
        for side in ('baseline', 'candidate'):
            row = pair[side]
            if type(row.get('resolved')) is not bool or type(row.get('calls')) is not int or row['calls'] < 1:
                raise ValueError('Expected a boolean resolution and positive recorded call count')
    baseline = sum(pair['baseline']['resolved'] for pair in pairs)
    candidate = sum(pair['candidate']['resolved'] for pair in pairs)
    baseline_calls = sum(pair['baseline']['calls'] for pair in pairs)
    candidate_calls = sum(pair['candidate']['calls'] for pair in pairs)
    regressions = [pair['instance_id'] for pair in pairs if pair['baseline']['resolved'] and not pair['candidate']['resolved']]
    reasons = []
    if regressions:
        reasons.append('Lost a baseline resolution')
    if candidate == 0:
        reasons.append('Candidate resolved no validation tasks')
    if not (candidate > baseline or candidate == baseline and candidate_calls * 10 <= baseline_calls * 9):
        reasons.append('No quality gain or at least 10 percent discovery-call reduction at preserved quality')
    return {'decision': 'rejected' if reasons else 'eligible_for_independent_evaluation',
            'promoted': False, 'selected_instances': len(expected), 'reasons': reasons,
            'regressions': regressions, 'baseline_resolved': baseline, 'candidate_resolved': candidate,
            'baseline_discovery_calls': baseline_calls, 'candidate_discovery_calls': candidate_calls,
            'warning': 'Exploratory validation only. Call comparison excludes training, proposal, and validation overhead; it is not net savings.'}


def measured_outcome(run: Path, official_report: Path, instance: str):
    """Check saved records and classify a supplied official single-task report."""
    audited = audit_candidate(run)
    if audited['instance_id'] != instance:
        raise ValueError('Candidate run is for a different instance')
    report = json.loads(official_report.read_text())
    if report.get('submitted_ids') != [instance] or report.get('total_instances') != 1:
        raise ValueError('Expected the corresponding single-instance official report')
    categories = ('resolved', 'unresolved', 'empty_patch', 'error', 'infra_failure', 'ambiguous_failure')
    for category in categories:
        ids = report.get(category+'_ids', [])
        if len(ids) != len(set(ids)) or set(ids) - {instance}:
            raise ValueError('Invalid instance IDs in official outcome')
        if report.get(category+'_instances') != len(ids):
            raise ValueError('Official summary count differs from its IDs')
    if any(instance in report.get(category+'_ids', []) for category in ('error', 'infra_failure', 'ambiguous_failure')):
        return {'status':'infrastructure_or_ambiguous', 'calls':audited['usage']['calls']}
    outcomes = [category for category in ('resolved','unresolved','empty_patch') if instance in report[category+'_ids']]
    if len(outcomes) != 1:
        raise ValueError('Expected exactly one final official outcome')
    if (outcomes[0] == 'empty_patch') != (audited['patch_bytes'] == 0):
        raise ValueError('Official empty-patch status differs from the candidate artifact')
    return {'status':'complete', 'resolved':outcomes[0] == 'resolved', 'outcome':outcomes[0],
            'calls':audited['usage']['calls'], 'usage':audited['usage'],
            'official_report_sha256':hashlib.sha256(official_report.read_bytes()).hexdigest(),
            'patch_sha256':audited['patch_sha256']}


def compare(plan_path: Path, proposal_path: Path, locations: dict):
    """Locations map each selected ID to baseline/candidate run and report paths."""
    plan = json.loads(plan_path.read_text())
    if hashlib.sha256(proposal_path.read_bytes()).hexdigest() != plan['proposal_sha256']:
        raise ValueError('Proposal differs from preregistered validation candidate')
    proposal = json.loads(proposal_path.read_text())
    expected = plan['validation_instances']
    if set(locations) - set(expected):
        raise ValueError('Unexpected validation instance')
    pairs, digests = [], set()
    for instance in expected:
        if instance not in locations:
            continue
        pair, manifests = {'instance_id':instance}, {}
        for side in ('baseline','candidate'):
            location = locations[instance].get(side)
            if location is None:
                pair[side] = {'status':'missing'}
                continue
            run, report = Path(location['run']), Path(location['report'])
            if not (run/'result.json').exists() or not report.exists():
                pair[side] = {'status':'missing'}
                continue
            result = json.loads((run/'result.json').read_text())
            if result.get('status') not in ('finished','budget_exhausted'):
                pair[side] = {'status':'infrastructure_or_runner_error'}
                continue
            manifest = json.loads((run/'manifest.json').read_text())
            manifests[side] = manifest
            if bool(manifest.get('retrieval')) != bool(plan.get('retrieval')):
                raise ValueError('Retrieval setting differs from registered comparison')
            if (manifest['seed'] != plan['seed'] or manifest['steps'] != plan['max_calls_per_instance']
                    or manifest['max_tokens_per_call'] != plan['max_tokens_per_call']):
                raise ValueError('Run differs from registered seed or budget')
            if manifest['model']['name'] != plan['model']:
                raise ValueError('Run used a different model')
            digests.add(manifest['model']['digest'])
            if side == 'candidate':
                registered = plan.get('candidate_implementation_overrides', {}).get(instance, plan['candidate_implementation_hashes'])
                if manifest['policy'] != proposal['policy'] or manifest['implementation'] != registered:
                    raise ValueError('Candidate policy or implementation differs from registration')
            elif manifest['policy'] != 'fixed sequential tool loop':
                raise ValueError('Expected the fixed baseline policy')
            pair[side] = measured_outcome(run,report,instance)
        if len(manifests) == 2:
            a,b = manifests['baseline'],manifests['candidate']
            if a['image_id'] != b['image_id'] or a['inputs_sha256'] != b['inputs_sha256']:
                raise ValueError('Paired runtime image or task input differs')
            if a['implementation']['prepared_workspace.py'] != b['implementation']['prepared_workspace.py']:
                raise ValueError('Paired workspace adapters differ')
            if a.get('retrieval_sha256') != b.get('retrieval_sha256'):
                raise ValueError('Paired retrieved source context differs')
        pairs.append(pair)
    if len(digests) > 1:
        raise ValueError('Model digest changed across the comparison')
    result = decide(expected,pairs)
    result.update(pairs=pairs, proposal_usage=proposal['usage']['policy'])
    result['cost_scope'] = 'Paired discovery and proposal costs shown separately. Training and interrupted infrastructure overhead remain in archived evidence; unknown in-flight token counts prevent an exact total.'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--proposal', type=Path, required=True)
    parser.add_argument('--locations', type=Path, required=True,
                        help='JSON mapping instance IDs to baseline/candidate objects with run and report paths')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = compare(args.plan,args.proposal,json.loads(args.locations.read_text()))
    rendered = json.dumps(result,indent=2) + '\n'
    if args.output:
        with args.output.open('x') as stream:
            stream.write(rendered)
    print(rendered,end='')


if __name__ == '__main__':
    main()
