import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from dream_rsi.benchmark_audit import IMPLEMENTATION_FILES, audit_candidate


class CandidateAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'model_calls').mkdir()
        (self.root/'implementation').mkdir()
        implementation = {}
        for name in IMPLEMENTATION_FILES:
            data = b'# fixture snapshot\n'
            (self.root/'implementation'/name).write_bytes(data)
            implementation[name] = hashlib.sha256(data).hexdigest()
        self.write('manifest.json', {'instance_id':'fixture', 'steps':2, 'seed':7,
                   'max_tokens_per_call':100, 'implementation':implementation})
        self.write('task.json', {'instance_id':'fixture'})
        self.write('prediction.jsonl', {'instance_id':'fixture', 'model_name_or_path':'fixture', 'model_patch':''})
        (self.root/'patch.diff').write_text('')
        for i, action in enumerate(({'action':'read','path':'missing.py'}, {'action':'finish'})):
            self.write(f'model_calls/step-{i:03d}.json', {'id':f'step-{i:03d}', 'role':'discovery',
                'request':{'model':'fixture','options':{'seed':7+i,'num_predict':100}},
                'response':{'message':{'content':json.dumps(action)}, 'prompt_eval_count':10, 'eval_count':5},
                'wall_seconds':1})
            self.write(f'step-{i:03d}.json', {'action':action,'observation':{'returncode':1} if i == 0 else {}})
        self.write('result.json', {'instance_id':'fixture','status':'finished','patch_bytes':0,
                   'usage':{'discovery':{'calls':2,'input_tokens':20,'output_tokens':10,'request_seconds':2,'errors':0}}})

    def write(self, name, value):
        (self.root/name).write_text(json.dumps(value))

    def test_empty_failed_search_is_not_presented_as_success(self):
        report = audit_candidate(self.root)
        self.assertEqual(report['failed_tool_actions'], 1)
        self.assertEqual(report['patch_bytes'], 0)
        self.assertEqual(report['usage']['calls'], 2)
        self.assertNotIn('resolved', report)

    def test_altered_action_patch_cost_and_snapshot_are_rejected(self):
        mutations = [
            ('step-000.json', {'action':{'action':'run','command':'fake'},'observation':{}}),
            ('prediction.jsonl', {'instance_id':'fixture','model_name_or_path':'fixture','model_patch':'fake'}),
            ('result.json', {'instance_id':'fixture','status':'finished','patch_bytes':0,'usage':{'discovery':{'calls':0}}}),
        ]
        for name, value in mutations:
            original = (self.root/name).read_bytes()
            with self.subTest(name=name):
                self.write(name,value)
                with self.assertRaises(ValueError): audit_candidate(self.root)
                (self.root/name).write_bytes(original)
        (self.root/'implementation/model.py').write_text('# changed')
        with self.assertRaisesRegex(ValueError, 'snapshot hash'):
            audit_candidate(self.root)
