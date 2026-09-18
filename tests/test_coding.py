import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from dream_rsi.code_workflow import selected_source
from dream_rsi.engine import DiscoveryAgent, online, replay
from dream_rsi.policy import Policy, PolicySpec
from dream_rsi.sandbox import DockerSandbox, SandboxUnavailable, TestResult, equivalent
from dream_rsi.tasks.coding import CodingTask, load_suite
from dream_rsi.types import Evaluation, Node, World

SUITE = Path(__file__).resolve().parents[1] / 'examples/code/workflows.json'


class MockSandbox:
    def inspect(self):
        return {"runtime": "fixture", "image": "TEST-FIXTURE"}

    def run(self, source, entrypoint, cases):
        # Wiring fixture, not an execution or performance claim.
        passed = len(cases) if 'CORRECT_FIXTURE' in source else 0
        return TestResult(passed, len(cases), [], 'completed', 0., 'TEST-FIXTURE')


class CodeTests(unittest.TestCase):
    def test_suite_splits_and_no_private_prompt_data(self):
        suite = load_suite(SUITE)
        self.assertEqual({p['split'] for p in suite['problems']}, {'train','validation','test'})
        task = CodingTask(suite, sandbox=MockSandbox(), problem_id='batch-items')
        case = task.case(10)
        case.private['hidden_tests'].append({'args':['DO_NOT_EXPOSE'], 'expected':'PRIVATE_MARKER'})
        prompt = task.prompt(case, case.baseline, [], 0, 0)
        self.assertNotIn('PRIVATE_MARKER', prompt)
        self.assertNotIn('DO_NOT_EXPOSE', prompt)
        self.assertNotIn('private', case.public())
        with self.assertRaises(ValueError):
            CodingTask(suite, split='validation', problem_id='batch-items')

    def test_generic_engine_replay_and_legacy_world_loading(self):
        class Transport:
            def generate(self, prompt, schema, seed, role, call_id, max_tokens):
                return {'source':'def batches(items, size):\n    return [] # CORRECT_FIXTURE\n', 'rationale':'fixture'}
        task = CodingTask(load_suite(SUITE), sandbox=MockSandbox(), problem_id='batch-items')
        policy = Policy(PolicySpec())
        with tempfile.TemporaryDirectory() as root:
            world, episode = online(policy, DiscoveryAgent(Transport(),task),'fixture',1,2,2,1,4,[],Path(root))
            stored = World.from_dict(json.loads((Path(root)/'world.json').read_text()))
            self.assertEqual(stored.task_name, 'python_code')
            self.assertEqual(stored.case_id, 'batch-items')
            self.assertEqual(stored.nodes[0].artifact, stored.nodes[0].source)
            self.assertEqual(replay(policy,stored,4).best_score, episode.best_score)
            self.assertTrue((Path(root)/'attempts/b000-d000/candidate.py').exists())
        legacy = {'name':'old','seed':1,'baseline_points':[0,1,2,3],'baseline_score':1.,'branch_count':1,'max_depth':1,'workers':1}
        self.assertEqual(World.from_dict(legacy).task_name, 'sum_difference')

    def test_select_on_visible_quality_without_oracle_tiebreaking(self):
        world = World('x',1,(),1.,1,1,1,baseline_artifact='baseline')
        world.nodes = [Node('n',0,0,None,(),'candidate','',Evaluation(1.,True),1,artifact='candidate')]
        self.assertEqual(selected_source(world), ('baseline',1.,None))
        world.baseline_score = 0.
        self.assertEqual(selected_source(world), ('candidate',1.,'n'))

    def test_persistent_code_loop_private_gate_and_distinct_problem_splits(self):
        from dream_rsi.lab import LabConfig, LabManager
        from test_experiment import FixtureModel
        from test_lab import edited
        from dream_rsi.types import save_json
        class CodeFixture(FixtureModel):
            def generate(self, prompt, schema, seed, role, call_id, max_tokens=600):
                response = super().generate(prompt, schema, seed, role, call_id, max_tokens)
                if role == "discovery":
                    response = {"source": "def fixture():\n    return 1 # CORRECT_FIXTURE\n", "rationale": "TEST FIXTURE"}
                    with self._lock:
                        record = next(r for r in self.records if r["id"] == call_id)
                        record["response"]["message"]["content"] = json.dumps(response)
                        save_json(self.log_dir / f"{call_id}.json", record)
                return response
        suite = load_suite(SUITE)
        for problem in suite["problems"]:
            problem["hidden_tests"] = [{"args": ["PRIVATE_INPUT_761"], "expected": "PRIVATE_OUTPUT_439"}]
        with tempfile.TemporaryDirectory() as root:
            manager = LabManager(Path(root), model_factory=CodeFixture)
            state = manager.create("Code fixture", LabConfig(task="python_code",branches=2,depth=2,revisions=1,validation_pairs=2), suite)
            sid = state["id"]
            with patch("dream_rsi.lab.DockerSandbox", MockSandbox), patch("dream_rsi.lab.improve", edited):
                manager.start(sid,1,64)
                manager._thread.join(5)
            state = manager.get(sid)
            self.assertEqual(state["status"], "idle", state["message"])
            self.assertEqual(state["champion"]["version"],1)
            cycle = state["cycles"][0]
            ids = [p["candidate"]["case_id"] for p in cycle["pairs"]]
            self.assertEqual(len(ids),len(set(ids)))
            train = manager.world(sid,state["history"][0])
            self.assertNotIn(train["case_id"],ids)
            self.assertEqual(train["task_private"]["split"],"train")
            for path in (Path(root)/"sessions"/sid/"model_calls").glob("*.json"):
                prompt=json.loads(path.read_text())["request"]["prompt"]
                self.assertNotIn("PRIVATE_INPUT_761",prompt)
                self.assertNotIn("PRIVATE_OUTPUT_439",prompt)
            manager.close()
            from dream_rsi.code_benchmark import benchmark
            state_path = Path(root)/"sessions"/sid/"state.json"
            before = state_path.read_bytes()
            destination = Path(root)/"benchmark"
            with patch("dream_rsi.code_benchmark.DockerSandbox",MockSandbox), patch("dream_rsi.code_benchmark.OllamaModel",CodeFixture):
                result=benchmark(Path(root),sid,destination)
            self.assertEqual(state_path.read_bytes(),before)
            self.assertEqual(result["summary"]["pairs"],4)
            self.assertEqual(result["summary"]["fixed_calls"],16)
            self.assertEqual(result["summary"]["candidate_calls"],8)
            self.assertEqual(result["summary"]["regressions"],0)
            final_ids={p["problem"] for p in result["pairs"]}
            self.assertTrue(final_ids.isdisjoint(ids+[train["case_id"]]))
            for path in (destination/"model_calls").glob("*.json"):
                prompt=json.loads(path.read_text())["request"]["prompt"]
                self.assertNotIn("PRIVATE_INPUT_761",prompt)
                self.assertNotIn("PRIVATE_OUTPUT_439",prompt)

    def test_invalid_suite_and_source(self):
        suite = load_suite(SUITE)
        suite['problems'][1]['id'] = suite['problems'][0]['id']
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'bad.json';path.write_text(json.dumps(suite))
            with self.assertRaises(ValueError): load_suite(path)
        task=CodingTask(load_suite(SUITE),sandbox=MockSandbox())
        self.assertFalse(task.evaluate_artifact('def broken(',task.case(1)).valid)
        with self.assertRaises(ValueError): task.artifact({'source':None})

    def test_sandbox_fails_closed_and_has_no_host_mounts(self):
        sandbox=DockerSandbox()
        with patch('dream_rsi.sandbox.subprocess.run', side_effect=FileNotFoundError):
            with self.assertRaises(SandboxUnavailable): sandbox.inspect()
        command=sandbox.command('test','sha256:test')
        for required in ('--network=none','--read-only','--user=65534:65534','--cap-drop=ALL','--pids-limit=32','--memory=256m','--pull=never'):
            self.assertIn(required,command)
        self.assertNotIn('-v',command)
        self.assertNotIn('--mount',command)
        self.assertNotIn('--privileged',command)

    def test_structural_equality_is_not_python_bool_equality(self):
        self.assertFalse(equivalent(True,1))
        self.assertFalse(equivalent({'x':[False]}, {'x':[0]}))
        self.assertTrue(equivalent(10**1000,10**1000))
        self.assertFalse(equivalent(float('nan'),float('nan')))


@unittest.skipUnless(os.getenv('DREAM_TEST_DOCKER') == '1','Set DREAM_TEST_DOCKER=1 to exercise the real isolated runtime')
class DockerExecutionTests(unittest.TestCase):
    def test_actual_pass_fail_exception_and_private_answer_separation(self):
        sandbox=DockerSandbox()
        result=sandbox.run('def add(a,b):\n    return a+b\n','add',[{'args':[2,3],'expected':5},{'args':[1,1],'expected':3}])
        self.assertEqual(result.passed,1)
        self.assertEqual(result.total,2)
        result=sandbox.run('def f():\n    raise ValueError("bad code")\n','f',[{'args':[],'expected':1}])
        self.assertEqual(result.passed,0)
        self.assertIn('ValueError',result.cases[0]['error'])
        # Guessing a passing-test count never substitutes for an actual answer.
        result=sandbox.run('def f():\n    return {"passed":999}\n','f',[{'args':[],'expected':'PRIVATE_VALUE_NOT_SENT'}])
        self.assertEqual(result.passed,0)

    def test_runtime_isolation(self):
        source='''import os, socket

def inspect_runtime():
    try:
        open('/write-to-root', 'w').write('no')
        writable = True
    except OSError:
        writable = False
    return {'uid': os.getuid(), 'interfaces': [name for _,name in socket.if_nameindex()], 'root_writable': writable}
'''
        result=DockerSandbox().run(source,'inspect_runtime',[{'args':[],'expected':{'uid':65534,'interfaces':['lo'],'root_writable':False}}])
        self.assertEqual(result.passed,1,result)

    def test_timeout_output_bound_and_container_cleanup(self):
        from types import SimpleNamespace
        import uuid
        # Scope cleanup assertions to these containers; another live workspace
        # may legitimately have its own generated program running concurrently.
        suffix = "test-cleanup-" + uuid.uuid4().hex
        with patch("dream_rsi.sandbox.uuid.uuid4", return_value=SimpleNamespace(hex=suffix)):
            result=DockerSandbox(timeout=2).run('def f():\n    while True: pass\n','f',[{'args':[],'expected':1}])
            self.assertEqual(result.status,'timeout')
            self.assertEqual(result.passed,0)
            result=DockerSandbox(output_limit=1024).run('import os\ndef f():\n    os.write(1,b"x"*100000)\n    return 1\n','f',[{'args':[],'expected':1}])
            self.assertEqual(result.status,'output_limit')
        names=subprocess.check_output(['docker','ps','-a','--filter','name=dream-rsi-'+suffix,'--format','{{.Names}}'],text=True)
        self.assertEqual(names.strip(),'')
