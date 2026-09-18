import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dream_rsi.engine import DiscoveryAgent, online, replay
from dream_rsi.policy import Policy, PolicySpec
from dream_rsi.tasks.repository import RepositoryTask, safe_path, snapshot, validate_task, test_summary
from dream_rsi.sandbox import DockerSandbox

EXAMPLE = Path(__file__).resolve().parents[1]/'examples/repository'


def task_spec():
    return json.loads((EXAMPLE/'task.json').read_text())


def fixed_files():
    return {
        'fulfilment/rates.py': "def shipping_cents(weight_grams):\n    if weight_grams < 0:\n        raise ValueError('negative weight')\n    return ((weight_grams + 999) // 1000) * 300\n",
        'fulfilment/checkout.py': "from .rates import shipping_cents\n\ndef total_cents(items, discount_percent=0):\n    subtotal = sum(i['unit_cents'] * i['quantity'] for i in items)\n    grams = sum(i['unit_grams'] * i['quantity'] for i in items)\n    return subtotal * (100 - discount_percent) // 100 + shipping_cents(grams)\n"
    }


class RepositoryTests(unittest.TestCase):
    def test_snapshot_allowlist_and_symlinks(self):
        spec = task_spec()
        files = snapshot(EXAMPLE, spec)
        self.assertEqual(set(files), {'fulfilment/__init__.py', 'fulfilment/rates.py', 'fulfilment/checkout.py', 'tests/test_checkout.py'})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'link.py').symlink_to(EXAMPLE/'fulfilment/rates.py')
            bad = {**spec, 'include':['*.py']}
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                snapshot(root, bad)
        missing = {**spec, 'include':['tests/*.py']}
        with self.assertRaisesRegex(ValueError, 'editable files'):
            snapshot(EXAMPLE, missing)

    def test_test_summary_rejects_skipped_and_unknown_failures(self):
        self.assertEqual(test_summary('Ran 7 tests in 0.1s\n\nOK (skipped=7)\n','unittest',0,1)[0],0)
        self.assertEqual(test_summary('Ran 7 tests in 0.1s\n\nOK\n','unittest',0,7)[0],1)
        self.assertEqual(test_summary('Ran 7 tests in 0.1s\n\nOK\n','unittest',1,7)[0],0)
        subtests = 'FAIL: test_a (t.T.test_a) (i=1)\nFAIL: test_a (t.T.test_a) (i=2)\nRan 7 tests in 0.1s\n\nFAILED (failures=2)\n'
        self.assertEqual(test_summary(subtests,'unittest',1,7)[0],6/7)
        self.assertEqual(test_summary('=== 1 failed, 3 passed in 0.1s ===','pytest',1,4)[0],.75)
        self.assertEqual(test_summary('=== 4 passed in 0.1s ===','pytest',0,4)[0],1)

    def test_path_and_test_protection(self):
        for path in ('../escape', '/tmp/escape', 'x/../y', '.git/config', '.env', 'a\\b', 'x\ny'):
            with self.assertRaises(ValueError): safe_path(path)
        spec = task_spec()
        with self.assertRaises(ValueError): validate_task({**spec, 'editable':spec['test_files']})
        with self.assertRaises(ValueError): validate_task({**spec, 'command':'python -m unittest'})
        task = RepositoryTask(spec, snapshot(EXAMPLE, spec))
        with self.assertRaises(ValueError): task.artifact({'files':{**fixed_files(), '../escape':'bad'}})
        with self.assertRaises(ValueError): task.artifact({'files':{**fixed_files(), 'tests/test_checkout.py':'pass'}})
        prompt = task.prompt(task.case(1), task.baseline, [], 0, 0)
        self.assertNotIn('class ShippingTests', prompt)
        self.assertNotIn('test_discount_excludes_shipping', prompt)
        with self.assertRaises(ValueError): task.evaluate_artifact(task.baseline, task.case(1), hidden=True)

    def test_patch_applies_with_no_trailing_newline_and_new_file(self):
        spec = task_spec()
        files = snapshot(EXAMPLE, spec)
        spec['editable'].extend(['fulfilment/new.py', 'fulfilment/empty.py'])
        task = RepositoryTask(spec, files)
        changed = {**fixed_files(), 'fulfilment/new.py':'VALUE = 3', 'fulfilment/empty.py':''}
        changed['fulfilment/rates.py'] = changed['fulfilment/rates.py'].rstrip('\n')
        patch = task.source(changed)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, content in files.items():
                p = root/name;p.parent.mkdir(parents=True, exist_ok=True);p.write_text(content)
            result = subprocess.run(['git', 'apply', '-'], input=patch, text=True, cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for name, content in changed.items(): self.assertEqual((root/name).read_text(), content)


@unittest.skipUnless(os.environ.get('DREAM_TEST_DOCKER') == '1', 'Enable real Docker checks')
class RepositoryDockerTests(unittest.TestCase):
    def test_real_multifile_repair_and_replay(self):
        spec = task_spec(); files = snapshot(EXAMPLE, spec); before = copy.deepcopy(files)
        task = RepositoryTask(spec, files)
        baseline = task.evaluate_artifact(task.baseline, task.case(1))
        self.assertLess(baseline.score, 1)
        self.assertEqual(baseline.diagnostics['test_count'], 7)
        self.assertTrue(baseline.diagnostics['protected_unchanged'])
        class Fixture:
            def generate(self, *args, **kwargs): return {'files': fixed_files()}
        with tempfile.TemporaryDirectory() as td:
            world, episode = online(Policy(PolicySpec()), DiscoveryAgent(Fixture(),task), 'repo-test', 1, 1, 1, 1, 1, [], Path(td))
            self.assertEqual(episode.best_score, 1)
            self.assertEqual(world.nodes[0].artifact, fixed_files())
            self.assertIn('diff --git',world.nodes[0].source)
            self.assertEqual(replay(Policy(PolicySpec()),world,1).decisions, world.decisions)
        self.assertEqual(snapshot(EXAMPLE, spec), before)

    def test_export_verify_and_tamper_rejection(self):
        from dream_rsi.repository_workflow import solve_repository, verify_repository
        class SavedFixture:
            def __init__(self, model, logs, base_url): self.logs = logs
            def inspect(self): return {'name':'test-fixture','digest':'test-fixture'}
            def usage(self): return {'discovery':{'calls':1}}
            def generate(self, prompt, schema, seed, role, call_id, max_tokens):
                response = {'files': fixed_files()}
                self.logs.mkdir(parents=True, exist_ok=True)
                (self.logs/(call_id+'.json')).write_text(json.dumps({'response':{'message':{'content':json.dumps(response)}}}))
                return response
        with tempfile.TemporaryDirectory() as td, patch('dream_rsi.repository_workflow.OllamaModel', SavedFixture):
            output = Path(td)/'run'
            result = solve_repository(EXAMPLE, EXAMPLE/'task.json', output, branches=1, depth=1)
            self.assertEqual(result.score, 1)
            self.assertEqual(verify_repository(output).score, 1)
            selected = json.loads((output/'selected-files.json').read_text())
            selected['fulfilment/rates.py'] += '# altered after evaluation\n'
            (output/'selected-files.json').write_text(json.dumps(selected))
            with self.assertRaisesRegex(ValueError, 'Selected patch differs'):
                verify_repository(output)

    def test_zero_tests_and_protected_file_mutation_fail(self):
        spec = task_spec(); files = snapshot(EXAMPLE, spec)
        spec['command'] = ['python','-c',"print('No tests collected')"]
        task = RepositoryTask(spec,files)
        self.assertEqual(task.evaluate_artifact(task.baseline,task.case(1)).score, 0)
        spec['command'] = ['python','-c',"from pathlib import Path; Path('tests/test_checkout.py').write_text(''); print('Ran 7 tests')"]
        task = RepositoryTask(spec,files)
        result = task.evaluate_artifact(task.baseline,task.case(1))
        self.assertEqual(result.score, 0)
        self.assertFalse(result.diagnostics['protected_unchanged'])

    def test_new_files_do_not_appear_in_baseline(self):
        spec = task_spec(); files = snapshot(EXAMPLE, spec)
        spec['editable'].append('fulfilment/new.py')
        spec['minimum_tests'] = 1
        spec['command'] = ['python', '-c', "from pathlib import Path; assert not Path('fulfilment/new.py').exists(); print('Ran 1 test in 0.1s\\n\\nOK')"]
        task = RepositoryTask(spec, files)
        self.assertNotIn('fulfilment/new.py', task.baseline)
        self.assertEqual(task.evaluate_artifact(task.baseline, task.case(1)).score, 1)

    def test_timeout_and_output_limit(self):
        spec = task_spec(); files = snapshot(EXAMPLE,spec)
        spec['command'] = ['python','-c','while True: pass']
        task = RepositoryTask(spec,files,DockerSandbox(timeout=2))
        self.assertEqual(task.evaluate_artifact(task.baseline,task.case(1)).diagnostics['status'],'timeout')
        spec['command'] = ['python','-c',"print('x'*40000)"]
        task = RepositoryTask(spec,files)
        result = task.evaluate_artifact(task.baseline,task.case(1))
        self.assertEqual(result.score,0)
        self.assertTrue(result.diagnostics['output_limit'])
