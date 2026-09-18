from __future__ import annotations

from dataclasses import asdict, dataclass

from .expressions import Expression
from .types import Action, Node


GLOBAL_NAMES = {"beta", "baseline", "global_best", "opened", "probes", "workers", "rounds", "legal_count"}
BRANCH_NAMES = GLOBAL_NAMES | {"is_root", "depth", "anchor", "latest", "gain", "stagnation", "failures", "last_failed", "successes", "remaining"}
PLAN_NAMES = {"beta", "hard_width", "hard_depth", "workers", "history_count", "last_gain", "last_work", "plateau_rounds"}


@dataclass(frozen=True)
class PolicySpec:
    name: str = "fixed_parallel_refine"
    rationale: str = "Open all available directions and refine uniformly to the shared cap."
    priority: str = "10 if is_root else -depth"
    eligible: str = "True"
    batch_size: str = "workers"
    width: str = "hard_width"
    depth: str = "hard_depth"
    beta: float = 0.6

    def __post_init__(self):
        for field in ("name", "rationale", "priority", "eligible", "batch_size", "width", "depth"):
            if not isinstance(getattr(self, field), str):
                raise ValueError(f"policy {field} must be a string")

    def to_dict(self):
        return asdict(self)

    def source(self) -> str:
        lines = [f"# {' '.join(self.name.splitlines())}", f"# {' '.join(self.rationale.splitlines())}", f"DEFAULT_BETA = {self.beta!r}", ""]
        for name, expression, allowed in [("priority", self.priority, BRANCH_NAMES), ("eligible", self.eligible, BRANCH_NAMES),
                                           ("batch_size", self.batch_size, GLOBAL_NAMES), ("plan_width", self.width, PLAN_NAMES), ("plan_depth", self.depth, PLAN_NAMES)]:
            lines += [f"def {name}({', '.join(sorted(allowed))}):", f"    return {expression}", ""]
        return "\n".join(lines)


class Policy:
    def __init__(self, spec: PolicySpec, beta: float | None = None):
        self.spec = spec
        self.beta = spec.beta if beta is None else beta
        if type(self.beta) not in (float, int) or not 0 <= self.beta <= 1:
            raise ValueError("beta must be a scalar in [0,1]")
        self.priority = Expression(spec.priority, BRANCH_NAMES)
        self.eligible = Expression(spec.eligible, BRANCH_NAMES)
        self.batch_size = Expression(spec.batch_size, GLOBAL_NAMES)
        self.width = Expression(spec.width, PLAN_NAMES)
        self.depth = Expression(spec.depth, PLAN_NAMES)

    def plan_grid(self, hard_width: int, hard_depth: int, workers: int, history: list[dict]) -> tuple[int, int]:
        plateau = 0
        for row in reversed(history):
            if row["gain"] > 1e-9:
                break
            plateau += 1
        facts = {"beta": self.beta, "hard_width": hard_width, "hard_depth": hard_depth, "workers": workers,
                 "history_count": len(history), "last_gain": history[-1]["gain"] if history else 0.0,
                 "last_work": history[-1]["calls"] if history else 0, "plateau_rounds": plateau}
        return (max(1, min(hard_width, int(self.width(facts)))), max(1, min(hard_depth, int(self.depth(facts)))))

    def select(self, observed: tuple[Node, ...], legal: tuple[Action, ...], baseline: float, workers: int,
               rounds: int, max_depth: int) -> tuple[list[Action], dict]:
        # Only immutable, revealed nodes reach the policy. No World/replay handle.
        successful = [n.evaluation.score for n in observed if n.evaluation.valid]
        global_facts = {"beta": self.beta, "baseline": baseline, "global_best": max([baseline] + successful),
                        "opened": len({n.branch for n in observed}), "probes": len(observed), "workers": workers,
                        "rounds": rounds, "legal_count": len(legal)}
        ranked, diagnostics = [], []
        for action in legal:
            trajectory = [n for n in observed if n.branch == action.branch]
            best, stagnation, last_gain = baseline, 0, 0.0
            for node in trajectory:
                score = node.evaluation.score if node.evaluation.valid else best
                last_gain = score - best
                stagnation = 0 if score > best + 1e-12 else stagnation + 1
                best = max(best, score)
            facts = {**global_facts, "is_root": not trajectory, "depth": len(trajectory), "anchor": best,
                     "latest": trajectory[-1].evaluation.score if trajectory else baseline, "gain": last_gain,
                     "stagnation": stagnation, "failures": sum(not n.evaluation.valid for n in trajectory),
                     "last_failed": bool(trajectory and not trajectory[-1].evaluation.valid),
                     "successes": sum(n.evaluation.valid for n in trajectory), "remaining": max_depth - len(trajectory)}
            eligible = bool(self.eligible(facts))
            priority = float(self.priority(facts)) if eligible else None
            diagnostics.append({"action": action.id, "eligible": eligible, "priority": priority, "features": facts})
            if eligible:
                ranked.append((priority, action))
        # Structural tie breaking is deterministic, never based on hidden scores.
        ranked.sort(key=lambda item: (-item[0], item[1].branch))
        batch_size = max(0, min(workers, int(self.batch_size(global_facts))))
        return [a for _, a in ranked[:batch_size]], {"candidates": diagnostics, "batch_size": batch_size}
