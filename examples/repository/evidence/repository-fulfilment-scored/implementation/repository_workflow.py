"""Repair a project snapshot and export a reviewable patch without touching its files."""
from dataclasses import asdict
import json
import hashlib
from pathlib import Path

from .code_workflow import selected_source
from .engine import DiscoveryAgent, online
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .sandbox import DockerSandbox
from .tasks.repository import RepositoryTask, snapshot, validate_task
from .types import save_json


def solve_repository(repo: Path, task_path: Path, output: Path, model='qwen2.5-coder:7b',
                     branches=2, depth=3, seed=2027, image='python:3.12-slim',
                     base_url='http://localhost:11434', timeout=60):
    if type(branches) is not int or type(depth) is not int or not 1 <= branches <= 8 or not 1 <= depth <= 8 or branches*depth > 32:
        raise ValueError('Use 1–8 directions/depth and at most 32 attempts')
    if task_path.stat().st_size > 131072:
        raise ValueError('Task specification exceeds 128 KiB')
    spec = validate_task(json.loads(task_path.read_text()))
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Refusing to overwrite an existing run')
    files = snapshot(repo, spec)
    sandbox = DockerSandbox(image=image, timeout=timeout)
    runtime = sandbox.inspect()
    task = RepositoryTask(spec, files, sandbox)
    model_client = OllamaModel(model, output/'model_calls', base_url)
    metadata = model_client.inspect()
    output.mkdir(parents=True, exist_ok=True)
    save_json(output/'snapshot.json', {'task': spec, 'files': files})
    implementation = {}
    package = Path(__file__).parent
    for name in ('repository_workflow.py', 'tasks/repository.py', 'sandbox.py', 'engine.py', 'policy.py', 'model.py'):
        content = (package/name).read_bytes()
        target = output/'implementation'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        implementation[name] = hashlib.sha256(content).hexdigest()
    save_json(output/'manifest.json', {'task': task.name, 'snapshot_digest': task.digest,
               'model': metadata, 'runtime': runtime, 'seed': seed, 'branches': branches,
               'evaluator_version': 2, 'proposal_version': 1, 'implementation': implementation,
               'depth': depth, 'selection': 'Visible project tests only. No held-out quality claim.'})
    baseline = task.evaluate_artifact(task.baseline, task.case(seed))
    task.baseline_feedback = {'score': baseline.score, 'error': baseline.error,
                              'failures': baseline.diagnostics.get('failures', [])}
    save_json(output/'baseline.json', asdict(baseline))
    world, _ = online(Policy(PolicySpec()), DiscoveryAgent(model_client, task), 'repository-solve',
                      seed, branches, depth, 1, branches*depth, [], output/'world',
                      on_progress=lambda p: print(f"{p['calls']}/{branches*depth} attempts · project tests {'passing' if p['best'] == 1 else 'failing'}", flush=True))
    artifact, score, node = selected_source(world)
    final = task.evaluate_artifact(artifact, task.case(seed))
    if final.score != score:
        raise RuntimeError('Selected patch did not reproduce its recorded test result; inspect saved evidence')
    (output/'patch.diff').write_text(task.source(artifact))
    save_json(output/'selected-files.json', artifact)
    save_json(output/'result.json', {'snapshot_digest': task.digest, 'selected_node': node,
              'baseline': asdict(baseline), 'evaluation': asdict(final), 'usage': model_client.usage(),
              'warning': 'Project tests are visible, not independent holdouts. Review the patch before applying.'})
    print(f"Saved {output/'patch.diff'} · project tests {'passing' if final.score == 1 else 'failing'}", flush=True)
    return final
