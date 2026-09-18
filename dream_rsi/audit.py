"""Recompute evidence from disk rather than trusting summary claims."""
from pathlib import Path
import hashlib
import json
import math

from .engine import replay
from .experiment import comparison
from .improve import evaluate_policy
from .policy import Policy, PolicySpec
from .task import SumDifferenceTask
from .types import World


def audit_run(directory: Path) -> dict:
    results = json.loads((directory / "results.json").read_text())
    config = results["config"]
    task = SumDifferenceTask()
    checks = []
    worlds = {}
    calls = {}
    for path in sorted((directory / "model_calls").glob("*.json")):
        record = json.loads(path.read_text())
        assert record["id"] not in calls, "duplicate request id"
        calls[record["id"]] = record
    for path in sorted((directory / "worlds").glob("*/world.json")):
        world = World.from_dict(json.loads(path.read_text()))
        worlds[world.name] = world
        assert math.isclose(task.evaluate(world.baseline_points).score, world.baseline_score, abs_tol=1e-12)
        seen = {}
        for node in world.nodes:
            assert node.id not in seen, "duplicate node"
            assert node.parent_id is None if node.depth == 0 else node.parent_id in seen, "missing/forward parent"
            if node.parent_id is not None:
                parent = seen[node.parent_id]
                assert parent.branch == node.branch and parent.depth + 1 == node.depth, "broken lineage"
            assert node.depth < world.max_depth and node.branch < world.branch_count
            assert node.model_call_id in calls, "node missing real inference record"
            if node.evaluation.valid:
                measured = task.evaluate(node.points)
                assert measured.valid and measured.score == node.evaluation.score, "score differs from exact recomputation"
                assert measured.diagnostics == node.evaluation.diagnostics, "diagnostics differ"
                assert node.source == task.source(node.points), "source differs from evaluated artifact"
                raw = json.loads(calls[node.model_call_id]["response"]["message"]["content"])
                assert tuple(raw["points"]) == node.points, "artifact differs from model output"
            seen[node.id] = node
        actual = replay(Policy(PolicySpec(**world.policy)), world, config["budget"])
        assert actual.calls == len(world.nodes), "saved online policy does not revisit all of its own actions"
        assert actual.best_score == world.best_score, "online/replay best differs"
        assert [d["selected"] for d in actual.decisions] == [d["selected"] for d in world.decisions], "online/replay decisions differ"
    checks.append(f"Recomputed exact scores, lineage, model provenance and live/replay decisions for {len(worlds)} worlds")
    frozen = json.loads((directory / "frozen_policy.json").read_text())
    assert frozen == results["policy"]
    for pair in results["holdouts"]:
        for arm in ("dream", "fixed"):
            world = worlds[pair[arm]["name"]]
            assert pair[arm]["best"] == world.best_score
            assert pair[arm]["calls"] == len(world.nodes)
            if arm == "dream":
                assert world.policy == frozen, "holdout controller changed after freezing"
        assert worlds[pair["dream"]["name"]].baseline_points == worlds[pair["fixed"]["name"]].baseline_points
    assert comparison(results["holdouts"]) == results["comparison"], "comparison not reproducible"
    checks.append("Recomputed paired fresh comparison and verified frozen controller and matched initial sets")
    training_pool = []
    for row in results["training"]:
        training_pool.append(worlds[row["dream"]["name"]])
        folder = directory / "policies" / f"cycle-{row['cycle']:02d}"
        selection = json.loads((folder / "selection.json").read_text())
        measured_candidates = []
        for candidate in sorted(folder.glob("candidate_*.json")):
            if candidate.name.endswith("_rejected.json"):
                continue
            recorded = json.loads(candidate.read_text())
            measured = evaluate_policy(PolicySpec(**recorded["policy"]), training_pool, config["budget"], config["cost"], config["parallel_bonus"], objective=config["objective"])
            assert measured["selection_score"] == recorded["selection_score"], "candidate score not reproducible"
            measured_candidates.append(measured)
        winner = max(measured_candidates, key=lambda c: c["selection_score"])
        assert winner["policy"] == selection["selected"], "wrong selected candidate"
        assert selection["after"] >= selection["before"]
    checks.append("Recomputed every candidate's replay score and incumbent-preserving selection")
    for role, usage in results["usage"].items():
        records = [r for r in calls.values() if r["role"] == role]
        assert len(records) == usage["calls"], "usage count mismatch"
        for field, response_field in (("input_tokens", "prompt_eval_count"), ("output_tokens", "eval_count")):
            assert sum(r.get("response", {}).get(response_field, 0) for r in records) == usage[field]
    checks.append("Verified actual inference calls and token accounting from raw responses")
    manifest = directory / "source_snapshot" / "sha256.json"
    if manifest.exists():
        for name, expected in json.loads(manifest.read_text()).items():
            assert hashlib.sha256((manifest.parent / Path(name).name).read_bytes()).hexdigest() == expected
        checks.append("Verified archived source snapshot hashes")
    return {"status": "passed", "checks": checks, "worlds": len(worlds), "model_calls": len(calls)}
