from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any


def stable_seed(*parts: object) -> int:
    return int.from_bytes(hashlib.sha256(json.dumps(parts).encode()).digest()[:4], "big") & 0x7FFFFFFF


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


@dataclass(frozen=True)
class Evaluation:
    score: float
    valid: bool
    error: str | None = None
    diagnostics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Node:
    id: str
    branch: int
    depth: int
    parent_id: str | None
    points: tuple[int, ...]
    source: str
    rationale: str
    evaluation: Evaluation
    seed: int
    model_call_id: str | None = None
    artifact: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> Node:
        return cls(**{**value, "points": tuple(value["points"]), "evaluation": Evaluation(**value["evaluation"])})


@dataclass
class World:
    name: str
    seed: int
    baseline_points: tuple[int, ...]
    baseline_score: float
    branch_count: int
    max_depth: int
    workers: int
    nodes: list[Node] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    policy: dict = field(default_factory=dict)
    wall_seconds: float = 0.0
    hard_branch_count: int | None = None
    hard_max_depth: int | None = None
    planning_history: list[dict] | None = None
    task_name: str = "sum_difference"
    task_input: dict = field(default_factory=dict)
    task_private: dict = field(default_factory=dict)
    case_id: str = ""
    baseline_artifact: Any = None

    @property
    def best_score(self) -> float:
        return max([self.baseline_score] + [n.evaluation.score for n in self.nodes if n.evaluation.valid])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> World:
        return cls(**{**value, "baseline_points": tuple(value["baseline_points"]), "nodes": [Node.from_dict(n) for n in value.get("nodes", [])]})


@dataclass(frozen=True)
class Action:
    branch: int
    depth: int
    parent_id: str | None

    @property
    def id(self) -> str:
        return f"b{self.branch:03d}-d{self.depth:03d}"
