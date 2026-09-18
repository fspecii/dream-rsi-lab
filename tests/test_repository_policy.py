import unittest
from dream_rsi.repository_policy import BASELINE, ToolPolicy, validate_policy
from dream_rsi.benchmark_solver import ACTION_SCHEMA


def step(action, code=0):
    return {'action':action,'observation':{'returncode':code}}


class RepositoryPolicyTests(unittest.TestCase):
    def test_rejects_unbounded_and_mistyped_controls(self):
        for policy in ({**BASELINE,'shell':'rm anything'}, {**BASELINE,'history_window':True},
                       {**BASELINE,'history_window':24}, {**BASELINE,'search_first':'yes'}):
            with self.assertRaises(ValueError): validate_policy(policy)

    def test_requires_inspection_and_read_before_edit(self):
        policy = ToolPolicy({**BASELINE,'search_first':True,'read_before_edit':True})
        self.assertEqual(policy.choices([]), ['run'])
        history = [step({'action':'run','command':'git ls-files'})]
        self.assertNotIn('replace',policy.choices(history))
        history.append(step({'action':'read','path':'found.py'}))
        policy.check({'action':'replace','path':'found.py'},history)
        with self.assertRaisesRegex(ValueError,'Read this existing file'):
            policy.check({'action':'replace','path':'guessed.py'},history)
        self.assertEqual(ACTION_SCHEMA['properties']['action']['enum'],['run','read','replace','finish'])
        self.assertEqual(policy.schema(ACTION_SCHEMA,[])['properties']['action']['enum'],['run'])

    def test_repeated_failures_require_a_different_action(self):
        policy = ToolPolicy({**BASELINE,'avoid_repeated_failures':True})
        action = {'action':'read','path':'missing.py'}
        history = [step(action,1)]
        with self.assertRaisesRegex(ValueError,'already failed'): policy.check(action,history)
        history.append(step(action,1))
        self.assertNotIn('read',policy.choices(history))
        policy.check({'action':'run','command':'git ls-files'},history)
        # A successful read may be repeated; failure rejection is not a blanket ban.
        policy.check(action,[step(action)])
