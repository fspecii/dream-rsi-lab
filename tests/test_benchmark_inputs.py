import copy
import json
from pathlib import Path
import tempfile
import unittest

from dream_rsi.benchmark_inputs import PUBLIC_FIELDS, VERIFIED, prepare_inputs, write_inputs


class BenchmarkInputsTests(unittest.TestCase):
    def setUp(self):
        self.row = dict(instance_id='example__project-1', repo='example/project',
                        base_commit='a'*40, image='example/image:latest',
                        problem_statement='Fix the documented bug.', split='test', datasets=[VERIFIED],
                        patch='REFERENCE_SECRET', test_patch='TEST_SECRET', hints_text='HINT_SECRET',
                        FAIL_TO_PASS=['TEST_NAME_SECRET'], eval_script='EVALUATOR_SECRET',
                        future_solution_column={'answer': 'FUTURE_SECRET'})
        self.plan = {'dataset': VERIFIED, 'task_repo_commit': 'b'*40,
                     'instances': [{k: self.row[k] for k in ('instance_id', 'repo', 'base_commit', 'image')}]}

    def test_evaluator_fields_and_future_columns_never_cross_boundary(self):
        document = prepare_inputs([self.row], self.plan)
        self.assertEqual(set(document['tasks'][0]), set(PUBLIC_FIELDS))
        self.assertNotIn('SECRET', json.dumps(document))
        changed = copy.deepcopy(self.row)
        changed['patch'] = 'ANOTHER_REFERENCE'
        self.assertEqual(document, prepare_inputs([changed], self.plan))
        changed['problem_statement'] += ' With details.'
        self.assertNotEqual(document['inputs_sha256'], prepare_inputs([changed], self.plan)['inputs_sha256'])

    def test_missing_duplicate_or_changed_instances_fail_closed(self):
        for rows in ([], [self.row, self.row], [{**self.row, 'base_commit': 'c'*40}],
                     [{**self.row, 'datasets': []}], [{**self.row, 'split': 'train'}]):
            with self.subTest(rows=len(rows)), self.assertRaises(ValueError):
                prepare_inputs(rows, self.plan)

    def test_existing_inputs_are_not_overwritten(self):
        document = prepare_inputs([self.row], self.plan)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'inputs.json'
            write_inputs(path, document)
            with self.assertRaises(FileExistsError):
                write_inputs(path, {'replaced': True})
            self.assertEqual(json.loads(path.read_text()), document)
