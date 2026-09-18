import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from dream_rsi.lab import LabConfig, LabManager, promotion_check
from dream_rsi.policy import PolicySpec
from dream_rsi.server import LabServer, recorded_example
from dream_rsi.types import save_json
from test_experiment import FixtureModel


def edited(*args, **kwargs):
    return PolicySpec(name='test smaller grid', depth='1'), {'before': .9, 'after': 1.0}


class LabTests(unittest.TestCase):
    def test_gate_rejects_cheap_regression_invalid_incomplete_and_tie(self):
        pair = {'incumbent': {'best': 1., 'calls': 16}, 'candidate': {'best': 1., 'calls': 4, 'valid_attempts': 4}}
        pairs = [copy.deepcopy(pair), copy.deepcopy(pair)]
        self.assertTrue(promotion_check(pairs, 2)['accepted'])
        pairs[1]['candidate']['best'] = .99
        self.assertFalse(promotion_check(pairs, 2)['accepted'])
        self.assertFalse(promotion_check([pair], 2)['accepted'])
        pairs[1]['candidate']['best'] = 1.
        pairs[1]['candidate']['valid_attempts'] = 0
        self.assertFalse(promotion_check(pairs, 2)['accepted'])
        pair['candidate']['calls'] = 16
        self.assertFalse(promotion_check([pair, pair], 2)['accepted'])

    def test_promotion_persistence_rollback_and_separation(self):
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=FixtureModel)
            sid = manager.create('Test only', LabConfig(branches=2, depth=2, revisions=1, validation_pairs=2))['id']
            with patch('dream_rsi.lab.improve', edited):
                manager.start(sid, 1, 64)
                manager._thread.join(5)
            state = manager.get(sid)
            self.assertEqual(state['status'], 'idle', state['message'])
            self.assertEqual(state['champion']['version'], 1)
            self.assertEqual(len(state['cycles'][0]['pairs']), 2)
            self.assertEqual(len(state['history']), 1)
            self.assertIn('-live-', state['history'][0])
            self.assertEqual(state['usage']['calls'], 16)
            manager.close()
            manager = LabManager(Path(root), model_factory=FixtureModel)
            self.assertEqual(manager.get(sid)['champion']['version'], 1)
            restored = manager.restore(sid, 0)
            self.assertEqual(restored['champion']['version'], 0)
            self.assertEqual(restored['usage']['calls'], 16)
            self.assertEqual(len(restored['versions']), 2)
            manager.close()

    def test_real_gate_keeps_champion_when_cheaper_candidate_loses_quality(self):
        class RegressingModel(FixtureModel):
            def generate(self, prompt, schema, seed, role, call_id, max_tokens=600):
                result = super().generate(prompt, schema, seed, role, call_id, max_tokens)
                if role == "discovery" and "-candidate-" in call_id:
                    result = {"points": [0, 1, 2, 3], "rationale": "TEST regression fixture"}
                    with self._lock:
                        record = next(r for r in self.records if r["id"] == call_id)
                        record["response"]["message"]["content"] = json.dumps(result)
                        save_json(self.log_dir / f"{call_id}.json", record)
                return result
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=RegressingModel)
            sid = manager.create("Regression", LabConfig(branches=2, depth=2, validation_pairs=2))["id"]
            with patch("dream_rsi.lab.improve", edited):
                manager.start(sid, 1, 64)
                manager._thread.join(5)
            state = manager.get(sid)
            self.assertEqual(state["status"], "idle", state["message"])
            self.assertEqual(state["champion"]["version"], 0)
            self.assertEqual(state["cycles"][0]["outcome"], "rejected")
            self.assertEqual(state["cycles"][0]["gate"]["quality_losses"], 2)
            self.assertEqual(len(state["versions"]), 1)
            self.assertEqual(len(state["history"]), 1)
            manager.close()

    def test_call_limit_resume_does_not_repeat_completed_episode(self):
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=FixtureModel)
            sid = manager.create('Budget test', LabConfig(revisions=1, validation_pairs=2))['id']
            with patch('dream_rsi.lab.improve', edited):
                manager.start(sid, 1, 16)
                manager._thread.join(5)
                state = manager.get(sid)
                self.assertEqual(state['status'], 'paused')
                self.assertEqual(state['active_cycle']['phase'], 'dream')
                self.assertEqual(state['champion']['version'], 0)
                live_path = state['history'][0]
                manager.close()
                manager = LabManager(Path(root), model_factory=FixtureModel)
                manager.start(sid, 1, 100)
                manager._thread.join(5)
            state = manager.get(sid)
            self.assertEqual(state['status'], 'idle', state['message'])
            self.assertEqual(state['history'], [live_path])
            self.assertEqual(state['cycles'][0]['attempts']['live'], 1)
            self.assertEqual(state['usage']['calls'], 56)
            manager.close()

    def test_pause_after_episode_and_failed_model_leave_champion_unchanged(self):
        entered, release = threading.Event(), threading.Event()
        class BlockingModel(FixtureModel):
            def generate(self, *args, **kwargs):
                entered.set()
                release.wait(3)
                return super().generate(*args, **kwargs)
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=BlockingModel)
            sid = manager.create('Pause test', LabConfig(branches=2, depth=2))['id']
            manager.start(sid)
            self.assertTrue(entered.wait(2))
            manager.pause(sid)
            release.set()
            manager._thread.join(5)
            state = manager.get(sid)
            self.assertEqual(state['status'], 'paused')
            self.assertEqual(len(state['history']), 1)
            self.assertEqual(state['champion']['version'], 0)
            manager.discard_pending(sid)
            self.assertEqual(manager.get(sid)['cycles'][0]['outcome'], 'discarded')
            manager.close()
        class MissingModel(FixtureModel):
            def inspect(self):
                raise RuntimeError('model unavailable')
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=MissingModel)
            sid = manager.create('Failure test', LabConfig())['id']
            manager.start(sid)
            manager._thread.join(5)
            self.assertEqual(manager.get(sid)['status'], 'failed')
            self.assertEqual(manager.get(sid)['champion']['version'], 0)
            manager.close()

    def test_lock_restart_recovery_and_path_containment(self):
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root))
            with self.assertRaises(RuntimeError):
                LabManager(Path(root))
            sid = manager.create('Recovery', LabConfig())['id']
            with self.assertRaises(ValueError):
                manager.world(sid, '../../../world.json')
            state = manager.get(sid)
            state['status'] = 'running'
            save_json(Path(root)/'sessions'/sid/'state.json', state)
            manager.close()
            manager = LabManager(Path(root))
            self.assertEqual(manager.get(sid)['status'], 'interrupted')
            manager.close()

    def test_http_assets_token_origin_and_creation(self):
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root))
            server = LabServer(('127.0.0.1', 0), manager)
            worker = threading.Thread(target=server.serve_forever)
            worker.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                for asset in ('/', '/app.js', '/style.css', '/favicon.svg', '/api/example'):
                    with urllib.request.urlopen(base+asset) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read())
                request = urllib.request.Request(base+'/api/sessions', data=b'{"name":"HTTP test"}', headers={'Content-Type':'application/json'})
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                self.assertEqual(error.exception.code, 403)
                error.exception.close()
                request.add_header('X-Lab-Token', server.token)
                request.add_header('Origin', 'https://untrusted.example')
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(request)
                error.exception.close()
                request.remove_header('Origin')
                with urllib.request.urlopen(request) as response:
                    self.assertEqual(json.load(response)['name'], 'HTTP test')
            finally:
                server.shutdown()
                server.server_close()
                worker.join()
                manager.close()
        replay = recorded_example()['results']
        self.assertEqual(replay['fixed']['best_score'], replay['learned']['best_score'])
        self.assertLess(replay['learned']['calls'], replay['fixed']['calls'])
