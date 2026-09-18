"""Exact bounded instance of Appendix A's sum–difference objective."""
import math
import random

from .types import Evaluation


class SumDifferenceTask:
    name = "sum_difference"
    min_size = 4
    max_size = 20
    max_integer = 63

    def initial(self, seed: int) -> tuple[int, ...]:
        return tuple(sorted(random.Random(seed).sample(range(32), 8)))

    def evaluate(self, points: object) -> Evaluation:
        if not isinstance(points, (list, tuple)):
            return Evaluation(0.0, False, "construction must be a list of integers")
        if not self.min_size <= len(points) <= self.max_size:
            return Evaluation(0.0, False, f"need {self.min_size}..{self.max_size} entries")
        if any(type(x) is not int or not 0 <= x <= self.max_integer for x in points):
            return Evaluation(0.0, False, f"entries must be integers in [0, {self.max_integer}]")
        if len(set(points)) != len(points):
            return Evaluation(0.0, False, "duplicate entries: supply a set as distinct integers")
        sums = {a + b for a in points for b in points}
        differences = {a - b for a in points for b in points}
        score = math.log(len(sums) / len(points)) / math.log(len(differences) / len(points))
        return Evaluation(score, True, diagnostics={"size": len(points), "sumset_size": len(sums), "difference_set_size": len(differences)})

    @staticmethod
    def source(points: tuple[int, ...]) -> str:
        # A literal construction is an executable mathematical artifact, not an
        # unrestricted coding agent. This deliberate small-model restriction is
        # documented and does not affect the controller/replay interface.
        return "def construct():\n    return " + repr(list(points)) + "\n"
