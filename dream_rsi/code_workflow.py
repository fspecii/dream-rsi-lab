"""Runnable code-generation and repair workflow with held-out final assessment."""
from dataclasses import asdict
import json
from pathlib import Path

from .engine import DiscoveryAgent, online, world_summary
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .sandbox import DockerSandbox
from .tasks.base import TaskCase
from .tasks.coding import CodingTask, load_suite, PROPOSAL_VERSION
from .types import save_json


def selected_source(world):
    """Select on visible tests only. A tie retains the baseline/earliest winner."""
    source, score, node_id = world.baseline_artifact, world.baseline_score, None
    for node in world.nodes:
        if node.evaluation.valid and node.evaluation.score > score:
            source, score, node_id = node.artifact, node.evaluation.score, node.id
    return source, score, node_id


def assess_selected(task, world):
    source, score, node_id = selected_source(world)
    case = TaskCase(world.case_id, world.task_name, world.task_input, world.baseline_artifact, world.task_private)
    measured = task.evaluate_artifact(source, case, hidden=True)
    return {"node": node_id, "source": source, "visible_score": score, "hidden_score": measured.score,
            "hidden_valid": measured.valid, "assessment": asdict(measured)}


def solve(suite_path: Path, problem_id: str, output: Path, model="gemma3:4b", branches=2, depth=3,
          workers=1, seed=2027, base_url="http://localhost:11434", image="python:3.12-slim"):
    if type(branches) is not int or type(depth) is not int or not 1 <= branches <= 8 or not 1 <= depth <= 8 or branches*depth > 32 or not 1 <= workers <= 4:
        raise ValueError("Use 1–8 directions/depth, at most 32 attempts, and 1–4 workers")
    suite = load_suite(suite_path)
    problem = next((p for p in suite["problems"] if p["id"] == problem_id), None)
    if problem is None:
        raise ValueError("Unknown problem id; use code-tasks to list available problems")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"Refusing to overwrite existing output: {output}")
    sandbox = DockerSandbox(image=image)
    runtime = sandbox.inspect()
    transport = OllamaModel(model, output / "model_calls", base_url)
    metadata = transport.inspect()
    output.mkdir(parents=True, exist_ok=True)
    task = CodingTask(suite, split=problem["split"], sandbox=sandbox, problem_id=problem_id)
    save_json(output / "manifest.json", {"task": task.name, "problem": problem_id, "suite_digest": task.digest,
                                       "model": metadata, "runtime": runtime, "seed": seed, "proposal_version": PROPOSAL_VERSION,
                                       "branches": branches, "depth": depth, "workers": workers,
                                       "selection": "Visible tests only; private tests assessed once after search."})
    # Snapshot the exact evaluator inputs locally for reproducibility.
    save_json(output / "suite.json", suite)
    policy = Policy(PolicySpec())
    world, episode = online(policy, DiscoveryAgent(transport, task), "code-solve", seed, branches, depth,
                            workers, branches*depth, [], output / "world", planning_history=[],
                            on_progress=lambda p: print(f"{p['calls']}/{branches*depth} attempts · visible tests {p['best']:.0%}", flush=True))
    selection = assess_selected(task, world)
    (output / "solution.py").write_text(selection["source"])
    result = {"problem": problem_id, "world": world_summary(world), "selection": selection, "usage": transport.usage()}
    save_json(output / "result.json", result)
    print(f"Saved {output / 'solution.py'} · visible {selection['visible_score']:.0%} · private {selection['hidden_score']:.0%}", flush=True)
    return result
