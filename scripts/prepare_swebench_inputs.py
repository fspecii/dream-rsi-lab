"""Run with the official SWE-bench environment and this project on PYTHONPATH."""
import argparse
import json
from pathlib import Path
import subprocess

from dream_rsi.benchmark_inputs import prepare_inputs, write_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-repo', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    head = subprocess.check_output(['git', '-C', str(args.task_repo), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(args.task_repo), 'status', '--porcelain'], text=True)
    if head != plan['task_repo_commit'] or dirty:
        raise ValueError('Task repository must be clean at the registered commit')
    # Imported only by the preparation command; the lab has no harness dependency.
    from swebench.task.repo import load_task_repo
    rows = load_task_repo(args.task_repo, [item['instance_id'] for item in plan['instances']])
    document = prepare_inputs(rows, plan)
    write_inputs(args.output, document)
    print(f"Prepared {len(document['tasks'])} public tasks; SHA256 {document['inputs_sha256']}")


if __name__ == '__main__':
    main()
