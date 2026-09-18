import os
import json
from unittest.mock import patch
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

from dream_rsi.prepared_workspace import PreparedWorkspace, bounded_process
from dream_rsi.sandbox import SandboxUnavailable


class BoundedProcessTests(unittest.TestCase):
    def test_output_and_time_are_bounded(self):
        result = bounded_process([sys.executable, '-c', 'print("x"*100000)'], limit=1024)
        self.assertEqual(result['status'], 'output_limit')
        self.assertEqual(len(result['stdout']), 1024)
        result = bounded_process([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.1)
        self.assertEqual(result['status'], 'timeout')


@unittest.skipUnless(os.environ.get('DREAM_TEST_PREPARED_BASE'), 'Set a prepared image containing Git and Python')
class PreparedWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = 'dream-prepared-fixture:' + uuid.uuid4().hex
        base = os.environ['DREAM_TEST_PREPARED_BASE']
        platform = subprocess.check_output(['docker', 'image', 'inspect', base, '--format', '{{.Os}}/{{.Architecture}}'], text=True).strip()
        dockerfile = f'''FROM {base}
USER root
RUN rm -rf /testbed && mkdir /testbed
WORKDIR /testbed
RUN git init -q && git config user.name Fixture && git config user.email fixture@example.invalid && git commit --allow-empty -qm ancestor && git tag v0.9 && printf 'def add(a, b):\\n    return a - b\\n' > calc.py && git add calc.py && git commit -qm base && git rev-parse HEAD > /fixture-base && git describe --tags --always > /fixture-description && printf 'future solution canary' > later.txt && git add later.txt && git commit -qm later && git tag v9.9 && git rev-parse HEAD > /fixture-future
'''
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'Dockerfile').write_text(dockerfile)
            built = subprocess.run(['docker', 'build', '--platform', platform, '--network=none', '-t', cls.image, directory], capture_output=True, text=True, timeout=120)
            if built.returncode:
                raise RuntimeError(built.stderr)
        cls.base = subprocess.check_output(['docker', 'run', '--rm', '--network=none', '--entrypoint=cat', cls.image, '/fixture-base'], text=True).strip()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['docker', 'image', 'rm', cls.image], capture_output=True, timeout=30, check=True)

    def test_repair_export_history_isolation_and_cleanup(self):
        with PreparedWorkspace(self.image, self.base) as workspace:
            name = workspace.name
            settings = subprocess.check_output(['docker', 'inspect', '--format', '{{.HostConfig.NetworkMode}} {{len .Mounts}} {{.HostConfig.CapDrop}}', name], text=True)
            self.assertEqual(settings.strip(), 'none 0 [ALL]')
            self.assertEqual(workspace.run('git rev-list --count --all')['stdout'].strip(), '2')
            self.assertEqual(workspace.run('git rev-parse HEAD')['stdout'].strip(), self.base)
            self.assertEqual(workspace.run('test "$(git describe --tags --always)" = "$(cat /fixture-description)"')['returncode'], 0)
            self.assertNotEqual(workspace.run('git cat-file -e "$(cat /fixture-future)"')['returncode'], 0)
            self.assertNotIn('v9.9', workspace.run('git tag')['stdout'])
            self.assertEqual(workspace.run('git remote')['stdout'], '')
            self.assertEqual(workspace.patch(), '')
            self.assertIn('return a - b', workspace.file_action({'action': 'read', 'path': 'calc.py'})['stdout'])
            self.assertNotEqual(workspace.run('python -c "from calc import add; assert add(2, 3) == 5"')['returncode'], 0)
            edited = workspace.file_action({'action': 'replace', 'path': 'calc.py', 'old': 'return a - b', 'new': 'return a + b'})
            self.assertEqual(edited['returncode'], 0, edited['stderr'])
            self.assertEqual(workspace.run('python -c "from calc import add; assert add(2, 3) == 5"')['returncode'], 0)
            self.assertIn('+    return a + b', workspace.patch())
        check = subprocess.run(['docker', 'inspect', name], capture_output=True)
        self.assertNotEqual(check.returncode, 0)
        # Original prepared image is unchanged.
        with PreparedWorkspace(self.image, self.base) as fresh:
            self.assertEqual(fresh.patch(), '')
            self.assertIn('return a - b', fresh.file_action({'action': 'read', 'path': 'calc.py'})['stdout'])

    def test_path_escape_and_ambiguous_edits_fail(self):
        with PreparedWorkspace(self.image, self.base) as workspace:
            for path in ('../fixture-base', '/fixture-base', '.git/config'):
                self.assertNotEqual(workspace.file_action({'action':'read', 'path':path})['returncode'], 0)
            workspace.run('ln -s /fixture-base escape.py')
            self.assertNotEqual(workspace.file_action({'action':'read', 'path':'escape.py'})['returncode'], 0)
            self.assertNotEqual(workspace.file_action({'action':'replace', 'path':'calc.py', 'old':'missing', 'new':'bad'})['returncode'], 0)

    def test_edit_feedback_disambiguates_without_modifying_source(self):
        with PreparedWorkspace(self.image, self.base) as workspace:
            workspace.run("printf 'def first():\\n    return 1\\ndef second():\\n    return 1\\n' > calc.py")
            before = workspace.patch()
            request = {'action':'replace', 'path':'calc.py', 'old':'return 1', 'new':'return 2'}
            ambiguous = workspace.file_action(request)
            feedback = json.loads(ambiguous['stdout'])
            self.assertEqual(ambiguous['returncode'], 1)
            self.assertEqual(feedback['error'], 'ambiguous_match')
            self.assertEqual(feedback['matches'], 2)
            self.assertEqual(feedback['match_lines'], [2, 4])
            self.assertEqual(workspace.patch(), before)
            request.update(old='def second():\n    return 1', new='def second():\n    return 2')
            self.assertEqual(workspace.file_action(request)['returncode'], 0)
            missing = workspace.file_action(request)
            feedback = json.loads(missing['stdout'])
            self.assertEqual(feedback['error'], 'missing_match')
            self.assertEqual(feedback['matches'], 0)
            self.assertIn('return 2', str(feedback['current_excerpts']))
            self.assertEqual(workspace.run('python -c "from calc import first, second; assert first() == 1 and second() == 2"')['returncode'], 0)

    def test_candidate_workflow_exports_logged_prediction(self):
        from dream_rsi.benchmark_inputs import prepare_inputs, VERIFIED
        from dream_rsi.benchmark_solver import generate_prediction, load_public_input
        row = dict(instance_id='fixture__calc-1', repo='fixture/calc', base_commit=self.base,
                   image=self.image, problem_statement='add(2, 3) should return 5.',
                   datasets=[VERIFIED], split='test')
        plan = {'dataset': VERIFIED, 'task_repo_commit': 'b'*40,
                'instances': [{k: row[k] for k in ('instance_id', 'repo', 'base_commit', 'image')}]}
        actions = [
            {'action':'read', 'path':'calc.py'},
            {'action':'replace', 'path':'calc.py', 'old':'return a - b', 'new':'return a + b'},
            {'action':'run', 'command':'python -c "from calc import add; assert add(2, 3) == 5"'},
            {'action':'finish', 'summary':'Fixed and checked addition'},
        ]
        class FixtureModel:
            def __init__(self, model, logs, base_url, timeout):
                self.logs, self.calls = logs, 0
            def inspect(self): return {'name':'fixture', 'digest':'fixture'}
            def usage(self): return {'discovery': {'calls':self.calls, 'input_tokens':0,
                'output_tokens':0, 'request_seconds':0, 'errors':0}}
            def generate(self, prompt, schema, seed, role, call_id, max_tokens):
                result = actions[self.calls]
                self.calls += 1
                self.logs.mkdir(exist_ok=True)
                (self.logs/(call_id+'.json')).write_text(json.dumps({'id':call_id,'role':role,
                    'request':{'model':'fixture','options':{'seed':seed,'num_predict':max_tokens},
                               'messages':[{'role':'user','content':prompt}]},
                    'response':{'message':{'content':json.dumps(result)}},'wall_seconds':0}))
                return result
        with tempfile.TemporaryDirectory() as directory, patch('dream_rsi.benchmark_solver.OllamaModel', FixtureModel):
            root = Path(directory)
            inputs = root/'inputs.json'
            document = prepare_inputs([row], plan)
            inputs.write_text(json.dumps(document))
            output = root/'run'
            prediction = generate_prediction(inputs, row['instance_id'], output, model='fixture', steps=4)
            self.assertIn('+    return a + b', prediction['model_patch'])
            self.assertEqual(json.loads((output/'result.json').read_text())['status'], 'finished')
            self.assertEqual(json.loads((output/'prediction.jsonl').read_text()), prediction)
            manifest = json.loads((output/'manifest.json').read_text())
            self.assertTrue(manifest['image_id'].startswith('sha256:'))
            self.assertEqual(manifest['steps'], 4)
            # A schema-violating model edit is rejected by the controller too.
            # Then the same model can read, repair, test, and finish normally.
            actions.insert(0, actions[1])
            policy_path = root/'policy.json'
            policy_path.write_text(json.dumps({'policy': {'search_first':False,
                'read_before_edit':True, 'avoid_repeated_failures':True, 'history_window':4}}))
            controlled = root/'controlled'
            generated = generate_prediction(inputs, row['instance_id'], controlled,
                                            model='fixture', steps=5, policy_path=policy_path)
            self.assertIn('+    return a + b', generated['model_patch'])
            rejected = json.loads((controlled/'step-000.json').read_text())
            self.assertIn('invalid_action', rejected['observation'])
            self.assertIn('repository_policy.py', json.loads((controlled/'manifest.json').read_text())['implementation'])
            from dream_rsi.benchmark_audit import audit_candidate
            audit_candidate(output)
            audit_candidate(controlled)
            actions.pop(0)
            retrieved = root/'retrieved'
            generate_prediction(inputs,row['instance_id'],retrieved,model='fixture',steps=4,retrieve_context=True)
            saved_context = json.loads((retrieved/'retrieval.json').read_text())
            self.assertEqual(saved_context['context']['files'][0]['path'],'calc.py')
            audit_candidate(retrieved)
            saved_context['context']['files'][0]['excerpt'] = 'tampered after inference'
            (retrieved/'retrieval.json').write_text(json.dumps(saved_context))
            with self.assertRaisesRegex(ValueError,'Retrieval context differs'):
                audit_candidate(retrieved)
            # A model ignoring the restricted schema cannot repeat failed edits.
            original_actions = list(actions)
            bad = {'action':'replace', 'path':'calc.py', 'old':'missing', 'new':'bad'}
            actions[:] = [bad, bad] + original_actions
            recovered = root/'recovered'
            generate_prediction(inputs,row['instance_id'],recovered,model='fixture',steps=6,retrieve_context=True)
            blocked = json.loads((recovered/'step-001.json').read_text())
            self.assertIn('Edit recovery requires', blocked['observation']['invalid_action'])
            last = json.loads((recovered/'step-005.json').read_text())
            self.assertEqual(last['action']['action'], 'finish')
            audit_candidate(recovered)
            actions[:] = original_actions
            with self.assertRaises(FileExistsError):
                generate_prediction(inputs, row['instance_id'], output, model='fixture', steps=4)
            document['tasks'][0]['patch'] = 'forbidden'
            inputs.write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError, 'Unexpected fields'):
                load_public_input(inputs, row['instance_id'])

    def test_bad_base_and_runaway_commands_remove_container(self):
        workspace = PreparedWorkspace(self.image, 'a'*40)
        with self.assertRaisesRegex(SandboxUnavailable, 'Base commit unavailable'):
            workspace.__enter__()
        self.assertFalse(workspace.active)
        for command, kwargs in [('sleep 30', {'timeout':1}), ('python -c "print(\'x\'*100000)"', {'output_limit':1024})]:
            with PreparedWorkspace(self.image, self.base, **kwargs) as workspace:
                with self.assertRaisesRegex(SandboxUnavailable, 'workspace removed'):
                    workspace.run(command)
                self.assertFalse(workspace.active)
                self.assertNotEqual(subprocess.run(['docker','inspect',workspace.name], capture_output=True).returncode, 0)
