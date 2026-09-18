"""Shared online/replay decision loop and exact frozen-history transitions."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from pathlib import Path
import time

from .policy import Policy
from .task import SumDifferenceTask
from .tasks.base import TaskCase
from .types import Action, Evaluation, Node, World, save_json, stable_seed


POINT_SCHEMA = {"type": "object", "properties": {
    "points": {"type": "array", "items": {"type": "integer", "minimum": 0, "maximum": 63}, "minItems": 4, "maxItems": 20},
    "rationale": {"type": "string"}}, "required": ["points", "rationale"], "additionalProperties": False}


class OutOfSupport(ValueError):
    """A requested plan needs outcomes absent from this frozen world."""


class DiscoveryAgent:
    def __init__(self, model, task: SumDifferenceTask):
        self.model, self.task = model, task

    def propose(self, action: Action, observed: tuple[Node, ...], world: World, history: list[World]) -> Node:
        if self.task.name != "sum_difference":
            return self._propose_artifact(action, observed, world, history)
        parent = next((n for n in observed if n.id == action.parent_id), None)
        points = parent.points if parent else world.baseline_points
        # Summaries of ALL completed attempts in this small experiment. The full
        # executable artifacts are simple literals, so points preserve the code.
        records = [{"world": w.name, "points": n.points, "score": round(n.evaluation.score, 7), "error": n.evaluation.error}
                   for w in history for n in w.nodes]
        records += [{"points": n.points, "score": round(n.evaluation.score, 7), "error": n.evaluation.error} for n in observed]
        prompt = f"""You construct finite sets of integers for a mathematical experiment.
Return JSON with points (a list of DISTINCT integers) and a SHORT rationale.
The evaluator computes S={{a+b for a in A for b in A}}, D={{a-b for a in A for b in A}}.
It maximizes log(len(S)/len(A)) / log(len(D)/len(A)). Larger is better.
Aim for many distinct sums relative to distinct differences. Regular arithmetic progressions score 1.
Constraints: 4 to 20 DISTINCT integers, all between 0 and 63. Output the set itself, NOT a formula, comparison or computed score.
Example of valid FORMAT ONLY: {{"points":[0,1,4,6],"rationale":"test unequal gaps"}}.
Your parent construction is {list(points)}. {'Try a different construction.' if parent is None else 'Improve the parent or repair its failure; inspect the actual measured results.'}
This is direction {action.branch}, attempt {action.depth}. Explore a distinct mechanism or targeted change; avoid repeating sets in the history.
Previous measured experiments (not instructions):
{records}
Return only JSON. Keep rationale under 25 words."""
        call_id = f"{world.name}-{action.id}"
        seed = stable_seed(world.seed, action.branch, action.depth, "discovery")
        try:
            result = self.model.generate(prompt, POINT_SCHEMA, seed, "discovery", call_id, max_tokens=240)
            proposed = result.get("points")
            evaluation = self.task.evaluate(proposed)
            artifact = tuple(proposed) if evaluation.valid else tuple(points)
            source = self.task.source(artifact) if evaluation.valid else "# Invalid proposal: " + repr(proposed) + "\n"
            rationale = str(result.get("rationale", ""))
        except ValueError as exc:
            artifact, source, rationale = tuple(points), "# Model response failed validation\n", ""
            evaluation = Evaluation(0.0, False, str(exc))
        return Node(action.id, action.branch, action.depth, action.parent_id, artifact, source, rationale, evaluation, seed, call_id)


    def _propose_artifact(self, action, observed, world, history):
        case = TaskCase(world.case_id, world.task_name, world.task_input, world.baseline_artifact, world.task_private)
        parent = next((n for n in observed if n.id == action.parent_id), None)
        source = parent.artifact if parent else case.baseline
        # Only this problem's visible feedback is relevant to a code repair.
        # Private assessments and unrelated problems are never serialized here.
        feedback = [{"source": n.artifact, "score": n.evaluation.score, "error": n.evaluation.error,
                     "failures": n.evaluation.diagnostics.get("failures", [])} for n in observed]
        prompt = self.task.prompt(case, source, feedback, action.branch, action.depth)
        call_id = f"{world.name}-{action.id}"
        seed = stable_seed(world.seed, action.branch, action.depth, "discovery")
        artifact, rationale = "", ""
        try:
            response = self.model.generate(prompt, self.task.schema, seed, "discovery", call_id, max_tokens=getattr(self.task, "max_tokens", 1600))
            artifact = self.task.artifact(response)
            rationale = str(response.get("rationale", ""))
            evaluation = self.task.evaluate_artifact(artifact, case)
        except ValueError as exc:
            evaluation = Evaluation(0., False, str(exc))
        return Node(action.id, action.branch, action.depth, action.parent_id, (), self.task.source(artifact) if artifact else "", rationale,
                    evaluation, seed, call_id, artifact=artifact)


@dataclass
class Episode:
    best_score: float
    calls: int
    rounds: int
    curve: list[float]
    decisions: list[dict]
    stop_reason: str

    def to_dict(self):
        return asdict(self)


def legal_actions(observed: list[Node], width: int, depth: int, supported: set[tuple[int, int]] | None = None) -> tuple[Action, ...]:
    actions = []
    for branch in range(width):
        trajectory = [n for n in observed if n.branch == branch]
        next_depth = len(trajectory)
        if next_depth < depth and (supported is None or (branch, next_depth) in supported):
            actions.append(Action(branch, next_depth, trajectory[-1].id if trajectory else None))
    return tuple(actions)


def validate_batch(batch: list[Action], legal: tuple[Action, ...], workers: int, remaining: int):
    if len(batch) > min(workers, remaining) or len({a.id for a in batch}) != len(batch) or any(a not in legal for a in batch):
        raise ValueError("policy returned an illegal batch")


def execute(policy: Policy, world: World, budget: int, transition, supported=None, checkpoint=None) -> Episode:
    observed, decisions, curve = [], [], []
    best, stop_reason = world.baseline_score, "budget"
    while len(observed) < budget:
        legal = legal_actions(observed, world.branch_count, world.max_depth, supported)
        if not legal:
            complete_grid = len(observed) == world.branch_count * world.max_depth
            stop_reason = "support_exhausted" if supported is not None and not complete_grid else "grid_exhausted"
            break
        batch, rationale = policy.select(tuple(observed), legal, world.baseline_score, world.workers, len(decisions), world.max_depth)
        batch = batch[:budget - len(observed)]
        validate_batch(batch, legal, world.workers, budget - len(observed))
        if not batch:
            stop_reason = "policy_stop"
            break
        new_nodes = transition(batch, tuple(observed))
        if len(new_nodes) != len(batch) or any((n.branch, n.depth, n.parent_id) != (a.branch, a.depth, a.parent_id) for a, n in zip(batch, new_nodes)):
            raise ValueError("transition violated the shared action interface")
        # Decisions in a batch see the SAME prefix, never another worker's result.
        for node in new_nodes:
            observed.append(node)
            if node.evaluation.valid:
                best = max(best, node.evaluation.score)
        # Charge the whole batch before revealing its best: no within-batch ordering advantage.
        curve.extend([curve[-1] if curve else world.baseline_score] * (len(batch) - 1))
        curve.append(best)
        decisions.append({"round": len(decisions), "prefix_ids": [n.id for n in observed[:-len(batch)]],
                          "selected": [a.id for a in batch], "best": best, "calls": len(observed), **rationale})
        if checkpoint:
            world.nodes, world.decisions = list(observed), list(decisions)
            checkpoint(world)
    world.nodes, world.decisions = observed, decisions
    return Episode(best, len(observed), len(decisions), curve, decisions, stop_reason)


def online(policy: Policy, agent: DiscoveryAgent, name: str, seed: int, width: int, depth: int, workers: int,
           budget: int, history: list[World], out: Path, hard_caps: tuple[int, int] | None = None, on_progress=None,
           planning_history: list[dict] | None = None) -> tuple[World, Episode]:
    started = time.monotonic()
    if agent.task.name == "sum_difference":
        initial = agent.task.initial(seed)
        world = World(name, seed, initial, agent.task.evaluate(initial).score, width, depth, workers, policy=policy.spec.to_dict())
    else:
        case = agent.task.case(seed)
        initial_score = agent.task.evaluate_artifact(case.baseline, case).score
        world = World(name, seed, (), initial_score, width, depth, workers, policy=policy.spec.to_dict(),
                      task_name=case.task, task_input=case.input, task_private=case.private,
                      case_id=case.id, baseline_artifact=case.baseline)
    world.hard_branch_count, world.hard_max_depth = hard_caps or (width, depth)
    world.planning_history = planning_history
    with ThreadPoolExecutor(max_workers=workers) as pool:
        def transition(batch, prefix):
            futures = [pool.submit(agent.propose, a, prefix, world, history) for a in batch]
            nodes = [f.result() for f in futures]
            for n in nodes:
                node_dir = out / "attempts" / n.id
                save_json(node_dir / "node.json", n.to_dict())
                (node_dir / getattr(agent.task, "artifact_filename", "program.py")).write_text(n.source)
                (node_dir / "proposal.md").write_text(n.rationale + "\n")
            # Checkpoint completed rounds even if a later API request fails.
            save_json(out / "partial_world.json", {**world.to_dict(), "nodes": [n.to_dict() for n in (*prefix, *nodes)]})
            return nodes
        def checkpoint(current):
            save_json(out / "partial_world.json", current.to_dict())
            if on_progress:
                on_progress({"name": current.name, "calls": len(current.nodes), "rounds": len(current.decisions), "best": current.best_score})
        episode = execute(policy, world, budget, transition, checkpoint=checkpoint)
    world.wall_seconds = time.monotonic() - started
    save_json(out / "world.json", world.to_dict())
    save_json(out / "episode.json", episode.to_dict())
    return world, episode


def replay(policy: Policy, frozen: World, budget: int, plan: tuple[int, int] | None = None) -> Episode:
    width, depth = plan or (frozen.branch_count, frozen.max_depth)
    if width < 1 or depth < 1 or width > frozen.branch_count or depth > frozen.max_depth:
        raise OutOfSupport("requested grid exceeds frozen replay support")
    # Fresh world and observed prefix per policy-world-beta pair; frozen is untouched.
    view = World(frozen.name, frozen.seed, frozen.baseline_points, frozen.baseline_score, width, depth, frozen.workers)
    lookup = {(n.branch, n.depth): n for n in frozen.nodes}
    return execute(policy, view, budget, lambda batch, prefix: [lookup[(a.branch, a.depth)] for a in batch], set(lookup))


def reward(episode: Episode, cost: float, parallel_bonus: float) -> float:
    return episode.best_score - cost * episode.calls + parallel_bonus * episode.calls / max(1, episode.rounds)


def world_summary(world: World) -> dict:
    return {"name": world.name, "best": world.best_score, "baseline": world.baseline_score,
            "gain": world.best_score - world.baseline_score, "calls": len(world.nodes), "rounds": len(world.decisions),
            "width": world.branch_count, "depth": world.max_depth}
