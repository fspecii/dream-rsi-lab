import unittest
from dream_rsi.benchmark_solver import recovery_required

class RepairRecoveryTests(unittest.TestCase):
    def test_failure_requires_successful_inspection(self):
        history = [{'action': {'action':'replace'}, 'observation': {'returncode':1}}]
        self.assertTrue(recovery_required(history))
        history.append({'action':{'action':'read'}, 'observation':{'returncode':1}})
        self.assertTrue(recovery_required(history))
        history.append({'action':{'action':'read'}, 'observation':{'returncode':0}})
        self.assertFalse(recovery_required(history))
        history.append({'action':{'action':'replace'}, 'observation':{'returncode':0}})
        self.assertFalse(recovery_required(history))

    def test_rejected_actions_do_not_erase_pending_recovery(self):
        history = [{'action': {'action':'replace'}, 'observation': {'invalid_action':'rejected'}}]
        history.append({'action':{'action':'finish'}, 'observation':{'invalid_action':'inspect first'}})
        self.assertTrue(recovery_required(history))
        history.append({'action':{'action':'run'}, 'observation':{'returncode':0}})
        self.assertFalse(recovery_required(history))
