"""Use the unmodified official harness against the candidate's exact prepared image."""
import argparse
import json
from pathlib import Path
from swebench.harness.run_evaluation import (
    _docker_client, load_instances, run_instances, write_run_metadata,
    make_run_report,
)

p = argparse.ArgumentParser()
p.add_argument('--candidate', type=Path, required=True)
p.add_argument('--task-repo', required=True)
p.add_argument('--run-id', required=True)
a = p.parse_args()
manifest = json.loads((a.candidate/'manifest.json').read_text())
prediction = json.loads((a.candidate/'prediction.jsonl').read_text())
task = json.loads((a.candidate/'task.json').read_text())
client = _docker_client()
assert client.images.get(task['image']).id == manifest['image_id'], 'Image changed'
assert prediction['instance_id'] == task['instance_id'] == manifest['instance_id']
instances = load_instances('SWE-bench/SWE-bench_Verified', 'test', [task['instance_id']], a.task_repo)
assert len(instances) == 1 and instances[0]['image'] == task['image']
write_run_metadata(a.run_id, 'SWE-bench/SWE-bench_Verified', 'test', a.task_repo)
predictions = {task['instance_id']: prediction}
run_instances(predictions, instances, 1, a.run_id, 1800, task_repo=a.task_repo)
make_run_report(predictions, instances, a.run_id, client)
