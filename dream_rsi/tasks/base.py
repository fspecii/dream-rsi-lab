"""JSON-serializable task contracts, with private evaluation data kept separate."""
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..types import Evaluation


@dataclass(frozen=True)
class TaskCase:
    id: str
    task: str
    input: dict
    baseline: Any
    # This field is evaluator-owned. Never serialize it into model prompts.
    private: dict = field(default_factory=dict, repr=False)

    def public(self):
        return {"id": self.id, "task": self.task, "input": self.input, "baseline": self.baseline}


class TaskAdapter(Protocol):
    name: str
    schema: dict
    artifact_filename: str

    def case(self, seed: int) -> TaskCase: ...
    def prompt(self, case: TaskCase, parent: Any, feedback: list[dict], branch: int, depth: int) -> str: ...
    def artifact(self, response: dict) -> Any: ...
    def evaluate_artifact(self, artifact: Any, case: TaskCase, *, hidden: bool = False) -> Evaluation: ...
    def source(self, artifact: Any) -> str: ...
