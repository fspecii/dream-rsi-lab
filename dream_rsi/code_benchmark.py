"""Frozen-controller comparisons on the code suite's untouched test split."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time

from .code_workflow import assess_selected
from .engine import DiscoveryAgent, online, world_summary
from .lab import LabConfig
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .sandbox import DockerSandbox
from .tasks.coding import CodingTask, validate_suite, PROPOSAL_VERSION
from .types import World, save_json, stable_seed


def benchmark(data_dir: Path, session_id: str, output: Path, repeats=1, base_url="http://localhost:11434"):
    if not re.fullmatch(r"[a-f0-9]{12}",session_id):
        raise ValueError("Invalid workspace id")
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError("Use 1–5 repetitions per test problem")
    directory = data_dir.resolve()/"sessions"/session_id
    state = json.loads((directory/"state.json").read_text())
    cfg = LabConfig(**state["config"])
    if cfg.task != "python_code" or state["status"] in ("running","pausing") or state["active_cycle"]:
        raise ValueError("Choose a stopped code workspace without a pending cycle")
    if not state["cycles"] or not state["model_metadata"]:
        raise ValueError("Complete at least one workspace cycle before benchmarking")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Benchmark output already exists")
    suite = validate_suite(json.loads((directory/"code_suite.json").read_text()))
    digest = hashlib.sha256(json.dumps(suite,sort_keys=True).encode()).hexdigest()
    if digest != state["task_metadata"]["suite_digest"]:
        raise ValueError("Suite differs from the training snapshot")
    problems = [p for p in suite["problems"] if p["split"] == "test"]
    if not problems:
        raise ValueError("The suite has no reserved test problems")
    sandbox = DockerSandbox()
    runtime = sandbox.inspect()
    if runtime != state["task_metadata"]["runtime"]:
        raise ValueError("Sandbox image differs from training")
    model = OllamaModel(cfg.model, output/"model_calls",base_url)
    metadata = model.inspect()
    if metadata["digest"] != state["model_metadata"]["digest"]:
        raise ValueError("Model differs from training")
    # Copy objects and data into the benchmark: a later workspace mutation cannot
    # change this frozen evaluation. Benchmark outcomes never update the workspace.
    history = [World.from_dict(json.loads((directory/p).read_text())) for p in state["history"]]
    selected = PolicySpec(**state["champion"]["policy"])
    fixed = PolicySpec()
    plan = [{"problem": p["id"],"seed":stable_seed(cfg.seed,session_id,"final-test",p["id"],r),"repeat":r}
            for r in range(repeats) for p in problems]
    output.mkdir(parents=True,exist_ok=True)
    save_json(output/"manifest.json", {"workspace": session_id,"created_at":datetime.now(timezone.utc).isoformat(),
                                      "model": metadata,"runtime":runtime,"suite_digest":digest,"config":state["config"],
                                      "proposal_version":PROPOSAL_VERSION,"training_proposal_versions":sorted({w.task_private.get("proposal_version",1) for w in history}),
                                      "champion":state["champion"],"plan":plan,"training_usage":state["usage"],
                                      "warning":"Small starter suite. No industry-wide or repository-level claim."})
    save_json(output/"suite.json",suite)
    save_json(output/"training_history.json",[w.to_dict() for w in history])
    pairs=[]
    started=time.monotonic()
    for i,row in enumerate(plan):
        task=CodingTask(suite,"test",sandbox,row["problem"])
        pair={**row}
        for arm in (("candidate","fixed") if i%2==0 else ("fixed","candidate")):
            policy=Policy(selected if arm=="candidate" else fixed)
            grid=policy.plan_grid(cfg.branches,cfg.depth,cfg.workers,[world_summary(w) for w in history])
            name=f"pair-{i:03d}-{arm}"
            print(f"{i+1}/{len(plan)} {row['problem']} · {arm}",flush=True)
            before=len(model.records)
            arm_start=time.monotonic()
            world,_=online(policy,DiscoveryAgent(model,task),name,row["seed"],*grid,cfg.workers,cfg.budget,
                           history,output/"worlds"/name,(cfg.branches,cfg.depth),planning_history=[world_summary(w) for w in history])
            result=assess_selected(task,world)
            save_json(output/"assessments"/f"{name}.json",result)
            calls=model.records[before:]
            pair[arm]={"private_score":result["hidden_score"],"visible_score":result["visible_score"],
                       "solved":result["hidden_valid"] and result["hidden_score"]==1.,"calls":len(calls),
                       "seconds":time.monotonic()-arm_start,
                       "input_tokens":sum(c.get("response",{}).get("prompt_eval_count",0) for c in calls),
                       "output_tokens":sum(c.get("response",{}).get("eval_count",0) for c in calls),"world":name}
        pairs.append(pair)
        save_json(output/"pairs.json",pairs)
    summary={**summarize(pairs), "policy_changed": selected.to_dict() != fixed.to_dict()}
    result={"pairs":pairs,"summary":summary,"usage":model.usage(),"seconds":time.monotonic()-started}
    save_json(output/"result.json",result)
    lines=["# Developer workflow benchmark","", "Frozen policy vs. fixed search on reserved test problems.",
           "Small starter suite; this does not establish industrial superiority.", "",
           "| Problem | Fixed private score | Candidate private score | Calls fixed → candidate |",
           "|---|---:|---:|---:|"]
    lines += [f"| {p['problem']} | {p['fixed']['private_score']:.2%} | {p['candidate']['private_score']:.2%} | {p['fixed']['calls']} → {p['candidate']['calls']} |" for p in pairs]
    lines += ["",f"Fully solved: fixed {summary['fixed_solved']}/{len(pairs)}, candidate {summary['candidate_solved']}/{len(pairs)}.",
              f"Quality regressions: {summary['regressions']}. Call reduction: {summary['call_reduction_percent']:.1f}%.",
              f"Training and validation cost an additional {state['usage']['calls']} model calls, excluded from the paired call reduction above.",
              "", "Raw source, prompts, runtime digest, evaluator inputs, token counts, and wall times are saved alongside this report."]
    if not summary["policy_changed"]:
        lines += ["", "No learned policy was accepted. This is a fixed-policy reproducibility check, not evidence of learned improvement."]
    (output/"REPORT.md").write_text("\n".join(lines)+"\n")
    return result


def summarize(pairs):
    fixed=sum(p["fixed"]["calls"] for p in pairs)
    candidate=sum(p["candidate"]["calls"] for p in pairs)
    return {"pairs":len(pairs),"fixed_solved":sum(p["fixed"]["solved"] for p in pairs),
            "candidate_solved":sum(p["candidate"]["solved"] for p in pairs),
            "regressions":sum(p["candidate"]["private_score"]+1e-12<p["fixed"]["private_score"] for p in pairs),
            "fixed_calls":fixed,"candidate_calls":candidate,"call_reduction_percent":100*(1-candidate/fixed) if fixed else 0.}
