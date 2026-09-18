from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import statistics
import shutil
import time

from .engine import DiscoveryAgent, online, world_summary
from .improve import improve
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .task import SumDifferenceTask
from .types import World, save_json, stable_seed


@dataclass(frozen=True)
class Config:
    model: str = "qwen3.5:0.8b"
    policy_model: str = ""
    policy_editor: str = "focused"
    continue_from: str = ""
    base_url: str = "http://localhost:11434"
    seed: int = 2026
    cycles: int = 3
    branches: int = 4
    depth: int = 4
    workers: int = 2
    budget: int = 16
    revisions: int = 3
    holdout_seeds: int = 4
    cost: float = 0.001
    parallel_bonus: float = 0.0005
    objective: str = "paper"

    def validate(self):
        if min(self.cycles, self.branches, self.depth, self.workers, self.budget, self.holdout_seeds) < 1 or self.revisions < 1:
            raise ValueError("all counts must be positive")
        if self.budget > self.branches * self.depth:
            raise ValueError("budget must not exceed branch_count * depth")
        if self.cost < 0 or self.parallel_bonus < 0:
            raise ValueError("reward coefficients must be nonnegative")
        if self.objective not in ("paper", "pareto"):
            raise ValueError("unknown objective")
        if self.policy_editor not in ("focused", "full"):
            raise ValueError("policy_editor must be focused or full")


def bootstrap_interval(values: list[float], seed=19, samples=2000) -> list[float]:
    rng = random.Random(seed)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return [means[int(samples * 0.025)], means[int(samples * 0.975)]]


def comparison(pairs: list[dict]) -> dict:
    differences = [p["dream"]["best"] - p["fixed"]["best"] for p in pairs]
    fixed_calls = sum(p["fixed"]["calls"] for p in pairs)
    dream_calls = sum(p["dream"]["calls"] for p in pairs)
    return {"pairs": len(pairs), "mean_quality_difference": statistics.mean(differences),
            "quality_difference_bootstrap_95": bootstrap_interval(differences),
            "fixed_calls": fixed_calls, "dream_calls": dream_calls,
            "call_reduction_fraction": 1 - dream_calls / fixed_calls if fixed_calls else 0.0,
            "fixed_mean_best": statistics.mean(p["fixed"]["best"] for p in pairs),
            "dream_mean_best": statistics.mean(p["dream"]["best"] for p in pairs),
            "matched_or_better_pairs": sum(d >= -1e-12 for d in differences),
            "demonstrated_equal_or_better_quality_with_fewer_calls": bool(dream_calls < fixed_calls and all(d >= -1e-12 for d in differences)),
            "interpretation": "Small paired exploratory experiment, not a statistically powered replication of the paper."}


def run(config: Config, out: Path, progress=print) -> dict:
    config.validate()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Refusing to overwrite an existing run: {out}")
    out.mkdir(parents=True, exist_ok=True)
    model = OllamaModel(config.model, out / "model_calls", config.base_url)
    metadata = model.inspect()
    developer = OllamaModel(config.policy_model or config.model, out / "model_calls", config.base_url)
    developer_metadata = developer.inspect()
    task, fixed, selected = SumDifferenceTask(), PolicySpec(), PolicySpec()
    history, fixed_history, training, selections = [], [], [], []
    imported_calls = {"discovery": 0, "policy": 0}
    if config.continue_from:
        parent = Path(config.continue_from).resolve()
        previous_config = json.loads((parent / "config.json").read_text())
        for field in ("model", "seed", "branches", "depth", "workers", "budget", "cost", "parallel_bonus", "objective"):
            if previous_config[field] != getattr(config, field):
                raise ValueError(f"continued experiment must preserve {field}")
        if previous_config["model_metadata"]["digest"] != metadata["digest"]:
            raise ValueError("discovery model digest changed since parent experiment")
        previous_developer = previous_config.get("policy_model_metadata", previous_config["model_metadata"])
        if previous_developer["digest"] != developer_metadata["digest"]:
            raise ValueError("policy-development model digest changed since parent experiment")
        previous = json.loads((parent / "training.json").read_text())
        training, selections = previous["cycles"], previous["selections"]
        if len(training) >= config.cycles:
            raise ValueError("--cycles must exceed the number of already completed training cycles")
        for row in training:
            for arm, pool in (("dream", history), ("fixed", fixed_history)):
                name = row[arm]["name"]
                source = parent / "worlds" / name
                pool.append(World.from_dict(json.loads((source / "world.json").read_text())))
                destination = out / "worlds" / name
                if not destination.exists():
                    shutil.copytree(source, destination)
        for cycle in range(len(training)):
            shutil.copytree(parent / "policies" / f"cycle-{cycle:02d}", out / "policies" / f"cycle-{cycle:02d}")
        # Import ONLY training requests. Old holdouts and results are never read,
        # copied into the new evidence, or used by either model.
        discovery_ids = {n.model_call_id for w in (*history, *fixed_history) for n in w.nodes}
        for path in sorted((parent / "model_calls").glob("*.json")):
            if path.stem not in discovery_ids and not path.stem.startswith("cycle-"):
                continue
            record = json.loads(path.read_text())
            owner = model if record["role"] == "discovery" else developer
            owner.records.append(record)
            imported_calls[record["role"]] += 1
            save_json(out / "model_calls" / path.name, record)
        selected = PolicySpec(**selections[-1]["selected"])
        save_json(out / "inherited_from.json", {"path": str(parent), "training_cycles": len(training), "imported_calls": imported_calls,
                                               "parent_config": previous_config, "holdouts_imported": False})
        if (parent / "source_snapshot").exists():
            shutil.copytree(parent / "source_snapshot", out / "inherited_source_snapshot")
    start_cycle = len(training)
    holdout_seed_plan = [stable_seed(config.seed, "holdout", start_cycle, i) if start_cycle else stable_seed(config.seed, "holdout", i)
                         for i in range(config.holdout_seeds)]
    def usage():
        return {"discovery": model.usage()["discovery"], "policy": developer.usage()["policy"]}
    snapshot = out / "source_snapshot"
    snapshot.mkdir()
    hashes = {}
    for file in sorted(Path(__file__).parent.glob("*.py")):
        data = file.read_bytes()
        (snapshot / file.name).write_bytes(data)
        hashes[file.name] = hashlib.sha256(data).hexdigest()
    save_json(snapshot / "sha256.json", hashes)
    save_json(out / "config.json", {**asdict(config), "model_metadata": metadata,
                                    "policy_model_metadata": developer_metadata,
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                    "heldout_seed_plan": holdout_seed_plan,
                                    "implementation": "independent constrained small-model demonstration",
                                    "task": {"name": "sum_difference", "max_integer": 63, "max_set_size": 20}})
    agent = DiscoveryAgent(model, task)
    started = time.monotonic()
    try:
        for cycle in range(start_cycle, config.cycles):
            seed = stable_seed(config.seed, "train", cycle)
            policy = Policy(selected)
            plan = policy.plan_grid(config.branches, config.depth, config.workers, [world_summary(w) for w in history])
            progress(f"Training cycle {cycle + 1}/{config.cycles}: live Dream policy {selected.name}, grid {plan}", flush=True)
            world, episode = online(policy, agent, f"train-{cycle:02d}-dream", seed, *plan, config.workers,
                                    config.budget, history, out / "worlds" / f"train-{cycle:02d}-dream", (config.branches, config.depth))
            history.append(world)
            if cycle == 0:
                # Exactly the SAME bootstrap trajectory, rather than hoping two
                # stochastic invocations yield the same first round.
                baseline_world = world
            else:
                progress(f"Training cycle {cycle + 1}: fixed-exploration control", flush=True)
                baseline_world, _ = online(Policy(fixed), agent, f"train-{cycle:02d}-fixed", seed, config.branches, config.depth,
                                            config.workers, config.budget, fixed_history, out / "worlds" / f"train-{cycle:02d}-fixed", (config.branches, config.depth))
            fixed_history.append(baseline_world)
            training.append({"cycle": cycle, "dream": world_summary(world), "fixed": world_summary(baseline_world), "shared_bootstrap": cycle == 0})
            progress(f"Dream best={world.best_score:.6f}, calls={len(world.nodes)}; fixed best={baseline_world.best_score:.6f}, calls={len(baseline_world.nodes)}. Replaying policies…", flush=True)
            selected, selection = improve(developer, selected, history, config.revisions, config.budget, config.cost,
                                          config.parallel_bonus, stable_seed(config.seed, cycle), out / "policies" / f"cycle-{cycle:02d}", config.objective, config.policy_editor)
            selections.append(selection)
            save_json(out / "training.json", {"cycles": training, "selections": selections})
            progress(f"Replay score {selection['before']:.6f} → {selection['after']:.6f}; {selection['valid_revisions']} valid revisions.", flush=True)
        # Freeze the policy BEFORE drawing and evaluating fresh holdout episodes.
        save_json(out / "frozen_policy.json", selected.to_dict())
        (out / "frozen_policy.py").write_text(selected.source())
        pairs = []
        plan = Policy(selected).plan_grid(config.branches, config.depth, config.workers, [world_summary(w) for w in history])
        for index in range(config.holdout_seeds):
            seed = holdout_seed_plan[index]
            pair = {"seed": seed}
            # Alternate ordering to reduce simple thermal/time-order confounding.
            for arm in (("dream", "fixed") if index % 2 == 0 else ("fixed", "dream")):
                spec = selected if arm == "dream" else fixed
                width, depth = plan if arm == "dream" else (config.branches, config.depth)
                progress(f"Fresh holdout {index + 1}/{config.holdout_seeds}: {arm}", flush=True)
                world, _ = online(Policy(spec), agent, f"holdout-{index:02d}-{arm}", seed, width, depth, config.workers,
                                   config.budget, history, out / "worlds" / f"holdout-{index:02d}-{arm}", (config.branches, config.depth))
                # Identical frozen history for BOTH arms. Holdouts never enter
                # policy-development context or another holdout's context.
                pair[arm] = world_summary(world)
            pairs.append(pair)
            save_json(out / "holdouts.json", pairs)
            progress(f"Holdout quality: dream={pair['dream']['best']:.6f}, fixed={pair['fixed']['best']:.6f}; calls {pair['dream']['calls']}/{pair['fixed']['calls']}", flush=True)
        result = {"config": asdict(config), "training": training, "selections": selections, "holdouts": pairs,
                  "comparison": comparison(pairs), "usage": usage(), "wall_seconds": time.monotonic() - started,
                  "model_metadata": metadata, "policy_model_metadata": developer_metadata, "policy": selected.to_dict(), "status": "complete"}
        result["imported_training_calls"] = imported_calls
        result["wall_time_scope"] = "This invocation only; imported training request time remains included in cumulative usage."
        save_json(out / "results.json", result)
        return result
    except Exception as exc:
        save_json(out / "failure.json", {"error": repr(exc), "usage": usage(), "elapsed_seconds": time.monotonic() - started})
        raise
    finally:
        save_json(out / "usage.json", usage())
