from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from dream_rsi.engine import DiscoveryAgent, execute, legal_actions, online, replay, reward, validate_batch
from dream_rsi.expressions import Expression
from dream_rsi.improve import evaluate_policy, improve
from dream_rsi.policy import BRANCH_NAMES, Policy, PolicySpec
from dream_rsi.task import SumDifferenceTask
from dream_rsi.types import Action, Evaluation, Node, World


def node(branch, depth, score, valid=True):
    return Node(f"b{branch:03d}-d{depth:03d}", branch, depth, None if depth == 0 else f"b{branch:03d}-d{depth-1:03d}",
                (0, 1, 3, 4), "def construct():\n    return [0,1,3,4]\n", "", Evaluation(score, valid), 1)


def fixture():
    return World("fixture", 1, (0, 1, 2, 3), 1.0, 2, 3, 2,
                 nodes=[node(0, 0, 1.02), node(1, 0, 1.01), node(0, 1, 1.02), node(1, 1, 1.04), node(0, 2, 1.02), node(1, 2, 1.04)])


class TaskTests(unittest.TestCase):
    def test_known_more_sums_than_differences(self):
        result = SumDifferenceTask().evaluate([0, 2, 3, 4, 7, 11, 12, 14])
        self.assertTrue(result.valid)
        self.assertGreater(result.score, 1)
        self.assertEqual(result.diagnostics["sumset_size"], 26)
        self.assertEqual(result.diagnostics["difference_set_size"], 25)

    def test_progression_and_invalid(self):
        task = SumDifferenceTask()
        self.assertEqual(task.evaluate([0, 1, 2, 3]).score, 1.0)
        for points in ([0, 1, 2, 2], [True, 1, 2, 3], [0, 1, 2, 64], "[0,1,2,3]"):
            self.assertFalse(task.evaluate(points).valid)

    def test_literal_artifact_matches_evaluated_construction(self):
        ns = {}
        exec(SumDifferenceTask.source((0, 1, 4, 6)), ns)
        self.assertEqual(ns["construct"](), [0, 1, 4, 6])


class PrefixTests(unittest.TestCase):
    def test_hidden_outcomes_cannot_change_prefix_decision(self):
        a, b = fixture(), fixture()
        b.nodes[-1] = node(1, 2, 99.0)
        policy = Policy(PolicySpec(priority="anchor + beta/(depth+1)", eligible="is_root or stagnation < 2"))
        ra, rb = replay(policy, a, 6), replay(policy, b, 6)
        self.assertEqual(ra.decisions[:2], rb.decisions[:2])

    def test_replay_does_not_mutate_world_and_resets(self):
        world = fixture()
        before = json.dumps(world.to_dict(), sort_keys=True)
        first, second = replay(Policy(PolicySpec()), world, 6), replay(Policy(PolicySpec()), world, 6)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(before, json.dumps(world.to_dict(), sort_keys=True))
        self.assertEqual(first.calls, 6)
        self.assertEqual(first.rounds, 3)

    def test_online_transition_and_replay_share_semantics(self):
        frozen = fixture()
        lookup = {(n.branch, n.depth): n for n in frozen.nodes}
        live = World("live", 1, frozen.baseline_points, 1, 2, 3, 2)
        episode = execute(Policy(PolicySpec()), live, 6, lambda batch, prefix: [lookup[(a.branch, a.depth)] for a in batch])
        self.assertEqual(episode.to_dict(), replay(Policy(PolicySpec()), frozen, 6).to_dict())

    def test_budget_is_calls_not_rounds(self):
        episode = replay(Policy(PolicySpec()), fixture(), 3)
        self.assertEqual((episode.calls, episode.rounds), (3, 2))
        self.assertEqual(len(episode.curve), 3)

    def test_no_within_batch_lookahead(self):
        episode = replay(Policy(PolicySpec()), fixture(), 6)
        self.assertEqual(episode.decisions[0]["prefix_ids"], [])
        self.assertEqual(episode.curve[0], 1.0)
        self.assertEqual(episode.curve[1], 1.02)

    def test_empty_policy_stops(self):
        episode = replay(Policy(PolicySpec(eligible="False")), fixture(), 6)
        self.assertEqual(episode.calls, 0)
        self.assertEqual(episode.best_score, 1.0)

    def test_irregular_support_terminates(self):
        world = fixture()
        world.nodes = world.nodes[:3]
        episode = replay(Policy(PolicySpec()), world, 6)
        self.assertEqual(episode.calls, 3)
        self.assertEqual(episode.stop_reason, "support_exhausted")
        with self.assertRaises(ValueError):
            replay(Policy(PolicySpec()), world, 6, (3, 3))

    def test_failed_child_retains_anchor_and_recovery_option(self):
        world = fixture()
        world.nodes[2] = node(0, 1, 0, False)
        result = replay(Policy(PolicySpec()), world, 6)
        features = next(c["features"] for c in result.decisions[2]["candidates"] if c["action"] == "b000-d002")
        self.assertEqual(features["anchor"], 1.02)
        self.assertTrue(features["last_failed"])

    def test_duplicate_and_parent_child_batches_rejected(self):
        legal = legal_actions([], 2, 3)
        with self.assertRaises(ValueError):
            validate_batch([legal[0], legal[0]], legal, 2, 6)
        with self.assertRaises(ValueError):
            validate_batch([legal[0], Action(0, 1, legal[0].id)], legal, 2, 6)


class ExpressionTests(unittest.TestCase):
    def test_forbids_access_to_hidden_data_and_unsafe_python(self):
        for source in ("world.nodes", "__import__('os')", "open('x')", "scores[0]", "[1]*999", "2**999", "best_future_score", "(lambda: 1)()"):
            with self.assertRaises(ValueError, msg=source):
                Expression(source, BRANCH_NAMES)

    def test_short_circuit_and_numeric_failure(self):
        self.assertFalse(Expression("False and 1/0", set())({}))
        self.assertEqual(Expression("max(2, int(beta*4))", {"beta"})({"beta": .8}), 3)
        with self.assertRaises(ValueError):
            Expression("1/0", set())({})

    def test_exported_python_matches_interpreter(self):
        spec = PolicySpec(priority="anchor-baseline + beta/(depth+1)")
        values = {name: 1 for name in BRANCH_NAMES}
        ns = {}
        exec(spec.source(), ns)
        self.assertEqual(ns["priority"](**values), Policy(spec).priority(values))


class ImprovementTests(unittest.TestCase):
    def test_focused_editor_changes_only_requested_expression(self):
        class Developer:
            def generate(self, *args, **kwargs):
                return {"expression": "is_root or depth < 2", "rationale": "fixture edit"}
        # 'depth' is available to the runtime eligibility expression even though
        # the focused prompt presents a smaller helpful subset of variables.
        with tempfile.TemporaryDirectory() as path:
            chosen, summary = improve(Developer(), PolicySpec(), [fixture()], 1, 6, .001, .0005, 1, Path(path), editor="focused")
        self.assertEqual(chosen.eligible, "is_root or depth < 2")
        self.assertEqual(chosen.priority, PolicySpec().priority)
        self.assertGreater(summary["after"], summary["before"])

    def test_offline_calls_only_policy_model_and_keeps_incumbent(self):
        class BadDeveloper:
            calls = []
            def generate(self, prompt, schema, seed, role, call_id, max_tokens):
                self.calls.append(role)
                return replace(PolicySpec(), eligible="False", name="stop_immediately").to_dict()
        model = BadDeveloper()
        with tempfile.TemporaryDirectory() as path:
            chosen, summary = improve(model, PolicySpec(), [fixture()], 2, 6, .001, .0005, 3, Path(path))
        self.assertEqual(chosen, PolicySpec())
        self.assertEqual(model.calls, ["policy", "policy"])
        self.assertGreaterEqual(summary["after"], summary["before"])
        self.assertEqual(summary["offline_discovery_calls"], 0)

    def test_invalid_policy_logged_not_deployed(self):
        class Developer:
            def generate(self, *args, **kwargs):
                return replace(PolicySpec(), priority="world.future").to_dict()
        with tempfile.TemporaryDirectory() as path:
            chosen, summary = improve(Developer(), PolicySpec(), [fixture()], 1, 6, .001, .0005, 1, Path(path))
            self.assertTrue((Path(path) / "candidate_01_rejected.json").exists())
        self.assertEqual(chosen, PolicySpec())
        self.assertEqual(summary["valid_revisions"], 0)

    def test_known_cost_saving_policy_wins_same_quality(self):
        baseline = evaluate_policy(PolicySpec(), [fixture()], 6, .001, .0005)
        stop = evaluate_policy(PolicySpec(eligible="depth < 2"), [fixture()], 6, .001, .0005)
        self.assertGreater(stop["selection_score"], baseline["selection_score"])
        self.assertEqual(stop["default"]["mean_best"], baseline["default"]["mean_best"])

    def test_replay_planning_uses_original_hard_caps_not_smaller_realized_grid(self):
        world = fixture()
        world.hard_branch_count = 4
        world.hard_max_depth = 6
        policy = PolicySpec(width="int(hard_width/2)", depth="int(hard_depth/2)")
        result = evaluate_policy(policy, [world], 6, .001, .0005)
        self.assertEqual(result["default"]["mean_calls"], 6)
        with self.assertRaises(ValueError):
            evaluate_policy(PolicySpec(), [world], 6, .001, .0005)

    def test_unsupported_beta_sweep_does_not_invalidate_supported_incumbent(self):
        world = fixture()
        world.hard_branch_count = 4
        world.hard_max_depth = 6
        policy = PolicySpec(width="max(1, int(hard_width * beta))", depth="max(1, int(hard_depth * beta))")
        result = evaluate_policy(policy, [world], 6, .001, .0005)
        self.assertTrue(result["default"]["supported"])
        high = next(e for e in result["sweep"] if e["beta"] == 1.0)
        self.assertFalse(high["supported"])
        self.assertIsNone(high["mean_score"])
        self.assertEqual(high["attainment_auc"], 0.0)

    def test_live_smoke_records_real_task_evaluations(self):
        class FixtureModel:
            def generate(self, prompt, schema, seed, role, call_id, max_tokens):
                return {"points": [0, 2, 3, 4, 7, 11, 12, 14], "rationale": "Test fixture, not LLM evidence"}
        with tempfile.TemporaryDirectory() as path:
            world, episode = online(Policy(PolicySpec()), DiscoveryAgent(FixtureModel(), SumDifferenceTask()), "smoke", 12, 2, 2, 2, 4, [], Path(path))
            restored = World.from_dict(json.loads((Path(path) / "world.json").read_text()))
            self.assertEqual(restored.to_dict(), world.to_dict())
            self.assertEqual(episode.calls, 4)
            self.assertEqual(replay(Policy(PolicySpec()), restored, 4).best_score, episode.best_score)


if __name__ == "__main__":
    unittest.main()
