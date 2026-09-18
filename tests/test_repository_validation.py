import unittest
from pathlib import Path
from dream_rsi.repository_validation import decide, measured_outcome


def pair(name, before, after, before_calls=24, after_calls=24):
    return {'instance_id':name, 'baseline':{'status':'complete','resolved':before,'calls':before_calls},
            'candidate':{'status':'complete','resolved':after,'calls':after_calls}}


class ValidationGateTests(unittest.TestCase):
    def test_actual_archived_empty_submission_is_a_completed_failure(self):
        evidence=Path(__file__).resolve().parents[1]/'examples/benchmarks/evidence'
        result=measured_outcome(evidence/'swebench-pilot-xarray-base-retry-20260918',
                                evidence/'xarray-official-results.json','pydata__xarray-6461')
        self.assertEqual(result['status'],'complete')
        self.assertFalse(result['resolved'])
        self.assertEqual(result['calls'],24)
        with self.assertRaises(ValueError):
            measured_outcome(evidence/'swebench-pilot-xarray-base-retry-20260918',
                             evidence/'django-official-results.json','pydata__xarray-6461')

    def test_cheaper_zero_quality_is_rejected(self):
        result=decide(['a','b'],[pair('a',False,False,24,1),pair('b',False,False,24,1)])
        self.assertEqual(result['decision'],'rejected')
        self.assertFalse(result['promoted'])

    def test_one_gain_cannot_hide_one_regression(self):
        result=decide(['a','b'],[pair('a',True,False,24,1),pair('b',False,True,24,1)])
        self.assertEqual(result['regressions'],['a'])
        self.assertEqual(result['decision'],'rejected')

    def test_missing_and_infrastructure_results_block_decision(self):
        self.assertEqual(decide(['a','b'],[pair('a',False,True)])['decision'],'incomplete')
        invalid=pair('b',False,False);invalid['candidate']['status']='infrastructure_or_runner_error'
        self.assertEqual(decide(['a','b'],[pair('a',False,True),invalid])['decision'],'incomplete')

    def test_quality_gain_or_matched_quality_call_savings_only_qualify_for_further_evaluation(self):
        for rows in ([pair('a',False,True),pair('b',False,False)],
                     [pair('a',True,True,24,20),pair('b',False,False,24,20)]):
            result=decide(['a','b'],rows)
            self.assertEqual(result['decision'],'eligible_for_independent_evaluation')
            self.assertFalse(result['promoted'])

    def test_duplicates_and_unregistered_tasks_fail(self):
        for rows in ([pair('a',False,True),pair('a',False,True)], [pair('other',False,True)]):
            with self.assertRaises(ValueError):decide(['a'],rows)
