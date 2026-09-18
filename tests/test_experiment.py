import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dream_rsi.audit import audit_run
from dream_rsi.experiment import Config, run
from dream_rsi.model import OllamaModel
from dream_rsi.report import write_report
from dream_rsi.types import save_json


class FixtureModel(OllamaModel):
    """Scripted transport used only for wiring/integrity tests, not scientific results."""
    def inspect(self):
        return {"name": self.model, "digest": "TEST-FIXTURE"}

    def generate(self, prompt, schema, seed, role, call_id, max_tokens=600):
        response = ({"points": [0, 2, 3, 4, 7, 11, 12, 14], "rationale": "TEST FIXTURE"} if role == "discovery" else
                    {"expression": "is_root or stagnation < 1", "rationale": "TEST FIXTURE"})
        record = {"id": call_id, "role": role, "request": {"model": self.model, "prompt": prompt, "seed": seed},
                  "response": {"message": {"content": json.dumps(response)}, "prompt_eval_count": 10, "eval_count": 10}, "wall_seconds": 0.0}
        with self._lock:
            save_json(self.log_dir / f"{call_id}.json", record)
            self.records.append(record)
        return response


class ExperimentTests(unittest.TestCase):
    def test_complete_loop_freeze_fresh_test_report_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "run"
            config = Config(cycles=2, branches=2, depth=4, budget=8, revisions=1, holdout_seeds=2)
            with patch("dream_rsi.experiment.OllamaModel", FixtureModel):
                result = run(config, out, progress=lambda *args, **kwargs: None)
            self.assertEqual(audit_run(out)["status"], "passed")
            self.assertTrue(write_report(out).exists())
            self.assertEqual(result["usage"]["policy"]["calls"], 2)
            self.assertGreaterEqual(result["comparison"]["call_reduction_fraction"], 0)
            config_record = json.loads((out / "config.json").read_text())
            self.assertEqual(config_record["heldout_seed_plan"], [r["seed"] for r in result["holdouts"]])
            train_seeds = {json.loads(p.read_text())["seed"] for p in (out / "worlds").glob("train*/world.json")}
            self.assertTrue(train_seeds.isdisjoint(config_record["heldout_seed_plan"]))
            for path in (out / "model_calls").glob("cycle-*.json"):
                prompt = json.loads(path.read_text())["request"]["prompt"]
                self.assertNotIn("holdout-", prompt)
            continued = Path(directory) / "continued"
            with patch("dream_rsi.experiment.OllamaModel", FixtureModel):
                next_result = run(Config(cycles=3, branches=2, depth=4, budget=8, revisions=1, holdout_seeds=2, continue_from=str(out)),
                                  continued, progress=lambda *args, **kwargs: None)
            self.assertEqual(audit_run(continued)["status"], "passed")
            next_plan = json.loads((continued / "config.json").read_text())["heldout_seed_plan"]
            self.assertTrue(set(next_plan).isdisjoint(config_record["heldout_seed_plan"]))
            self.assertGreater(next_result["imported_training_calls"]["discovery"], 0)
            self.assertEqual(next_result["imported_training_calls"]["policy"], 2)
            # Only training evidence is inherited, never a parent's heldout worlds.
            self.assertFalse(json.loads((continued / "inherited_from.json").read_text())["holdouts_imported"])
            # The integrity checker must reject a fabricated headline number.
            result["comparison"]["dream_calls"] = -1
            save_json(out / "results.json", result)
            with self.assertRaises(AssertionError):
                audit_run(out)

    def test_invalid_config_and_overwrite_protection(self):
        with self.assertRaises(ValueError):
            Config(branches=1, depth=1, budget=2).validate()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            (out / "existing.txt").write_text("keep me")
            with self.assertRaises(ValueError):
                run(Config(), out)
            self.assertEqual((out / "existing.txt").read_text(), "keep me")
