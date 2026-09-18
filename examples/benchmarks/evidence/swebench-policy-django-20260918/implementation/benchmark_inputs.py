"""Separate public SWE-bench task inputs from evaluator-only data.

This is an input boundary, not a claim that a pretrained model has never seen
the benchmark. The official harness remains responsible for final scoring.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


VERIFIED = 'SWE-bench/SWE-bench_Verified'
PUBLIC_FIELDS = ('instance_id', 'repo', 'base_commit', 'image', 'problem_statement')


def public_task(row: dict) -> dict:
    """Copy only documented solver inputs; ignore even unknown future columns."""
    if row.get('split') != 'test' or VERIFIED not in row.get('datasets', []):
        raise ValueError('Expected a SWE-bench Verified test instance')
    result = {}
    for field in PUBLIC_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'Missing public field: {field}')
        result[field] = value
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', result['instance_id']):
        raise ValueError('Invalid instance identifier')
    if not re.fullmatch(r'[0-9a-f]{40}', result['base_commit']):
        raise ValueError('Expected a complete base commit')
    if len(result['problem_statement'].encode()) > 131072:
        raise ValueError('Issue text exceeds 128 KiB')
    return result


def prepare_inputs(rows: list[dict], plan: dict) -> dict:
    """Require exactly the registered instances and preserve their order."""
    if plan.get('dataset') != VERIFIED:
        raise ValueError('Expected a Verified pilot plan')
    expected = plan.get('instances', [])
    if not expected or len({item['instance_id'] for item in expected}) != len(expected):
        raise ValueError('Pilot plan is empty or has duplicate instances')
    by_id = {}
    for row in rows:
        task = public_task(row)
        if task['instance_id'] in by_id:
            raise ValueError('Duplicate input instance')
        by_id[task['instance_id']] = task
    if set(by_id) != {item['instance_id'] for item in expected}:
        raise ValueError('Input instances differ from the registered pilot')
    tasks = []
    for item in expected:
        task = by_id[item['instance_id']]
        if any(task[field] != item[field] for field in ('repo', 'base_commit', 'image')):
            raise ValueError('Instance metadata differs from the registered pilot')
        tasks.append(task)
    canonical = json.dumps(tasks, sort_keys=True, ensure_ascii=False).encode()
    return {'schema_version': 1, 'dataset': VERIFIED,
            'task_repo_commit': plan['task_repo_commit'],
            'inputs_sha256': hashlib.sha256(canonical).hexdigest(), 'tasks': tasks}


def write_inputs(path: Path, document: dict):
    """Never replace inputs after a run has begun."""
    with path.open('x', encoding='utf-8') as output:
        json.dump(document, output, indent=2, ensure_ascii=False)
        output.write('\n')
