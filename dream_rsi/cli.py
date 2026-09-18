from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .engine import replay, world_summary
from .experiment import Config, run
from .model import OllamaModel
from .policy import Policy, PolicySpec
from .report import write_report
from .types import World


def main(argv=None):
    parser = argparse.ArgumentParser(description="Independent Dream-RSI small-model implementation")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Check local Ollama model availability")
    doctor.add_argument("--model", default=Config.model)
    doctor.add_argument("--base-url", default=Config.base_url)
    runner = commands.add_parser("run", help="Train, replay, then evaluate a frozen policy on fresh paired episodes")
    runner.add_argument("--output", type=Path, required=True)
    for name, default in asdict(Config()).items():
        runner.add_argument("--" + name.replace("_", "-"), type=type(default), default=default)
    replay_parser = commands.add_parser("replay", help="Evaluate a policy against a saved world without a model")
    replay_parser.add_argument("--world", type=Path, required=True)
    replay_parser.add_argument("--policy", type=Path, required=True)
    replay_parser.add_argument("--budget", type=int, default=16)
    replay_parser.add_argument("--history", type=Path, nargs="*", default=[], help="Earlier completed world JSON files for pre-episode planning")
    reporter = commands.add_parser("report", help="Regenerate a completed run's report")
    reporter.add_argument("directory", type=Path)
    inspector = commands.add_parser("inspect", help="Show a recorded discovery tree and the actual decisions")
    inspector.add_argument("world", type=Path)
    auditor = commands.add_parser("audit", help="Independently recompute a completed run's evidence")
    auditor.add_argument("directory", type=Path)
    lab = commands.add_parser("lab", help="Open the local workspace for persistent, validated self-improvement")
    lab.add_argument("--data-dir", type=Path, default=Path(".dream-rsi"))
    lab.add_argument("--port", type=int, default=8765)
    lab.add_argument("--open", action="store_true", help="Open your browser")
    lab.add_argument("--base-url", default=Config.base_url)
    code_tasks = commands.add_parser("code-tasks", help="Validate a code suite and list its generation/repair problems")
    code_tasks.add_argument("suite", type=Path)
    code_solve = commands.add_parser("code-solve", help="Generate or repair Python using isolated tests and private final checks")
    code_solve.add_argument("--suite", type=Path, required=True)
    code_solve.add_argument("--problem", required=True)
    code_solve.add_argument("--output", type=Path, required=True)
    code_solve.add_argument("--model", default="gemma3:4b")
    code_solve.add_argument("--branches", type=int, default=2)
    code_solve.add_argument("--depth", type=int, default=3)
    code_solve.add_argument("--workers", type=int, default=1)
    code_solve.add_argument("--seed", type=int, default=2027)
    code_solve.add_argument("--base-url", default=Config.base_url)
    code_solve.add_argument("--image", default="python:3.12-slim")
    code_bench = commands.add_parser("code-benchmark", help="Compare a frozen workspace policy on reserved code problems")
    code_bench.add_argument("--data-dir", type=Path, default=Path(".dream-rsi"))
    code_bench.add_argument("--workspace", required=True)
    code_bench.add_argument("--output", type=Path, required=True)
    code_bench.add_argument("--repeats", type=int, default=1)
    code_bench.add_argument("--base-url", default=Config.base_url)
    args = parser.parse_args(argv)
    try:
        if args.command == "code-benchmark":
            from .code_benchmark import benchmark
            result = benchmark(args.data_dir,args.workspace,args.output.resolve(),args.repeats,args.base_url)
            print(json.dumps(result["summary"],indent=2))
        elif args.command == "code-tasks":
            from .tasks.coding import load_suite
            suite = load_suite(args.suite)
            for problem in suite["problems"]:
                print(f"{problem['id']:<24} {problem['split']:<12} {len(problem['visible_tests'])} visible / {len(problem['hidden_tests'])} private tests")
        elif args.command == "code-solve":
            from .code_workflow import solve
            solve(args.suite, args.problem, args.output.resolve(), args.model, args.branches, args.depth,
                  args.workers, args.seed, args.base_url, args.image)
        elif args.command == "lab":
            from .server import serve
            serve(args.data_dir, args.port, args.open, args.base_url)
        elif args.command == "doctor":
            print(json.dumps(OllamaModel(args.model, Path("."), args.base_url).inspect(), indent=2))
        elif args.command == "run":
            options = vars(args).copy()
            del options["command"]
            out = options.pop("output").resolve()
            result = run(Config(**options), out)
            print(json.dumps(result["comparison"], indent=2))
            print("Report:", write_report(out), flush=True)
        elif args.command == "replay":
            frozen = World.from_dict(json.loads(args.world.read_text()))
            policy = Policy(PolicySpec(**json.loads(args.policy.read_text())))
            if args.budget < 1:
                raise ValueError("budget must be positive")
            history = [world_summary(World.from_dict(json.loads(path.read_text()))) for path in args.history]
            plan = policy.plan_grid(frozen.hard_branch_count or frozen.branch_count,
                                    frozen.hard_max_depth or frozen.max_depth, frozen.workers, history)
            episode = replay(policy, frozen, args.budget, plan)
            print(json.dumps({k: v for k, v in episode.to_dict().items() if k != "decisions"}, indent=2))
        elif args.command == "inspect":
            world = World.from_dict(json.loads(args.world.read_text()))
            print(f"{world.name}: baseline={world.baseline_score:.6f}, best={world.best_score:.6f}")
            for branch in range(world.branch_count):
                trajectory = [n for n in world.nodes if n.branch == branch]
                scores = [f"{n.evaluation.score:.6f}" if n.evaluation.valid else "FAILED" for n in trajectory]
                print(f"  Branch {branch}: " + (" -> ".join(scores) or "unopened"))
            for d in world.decisions:
                print(f"  Round {d['round']+1}: reveal {', '.join(d['selected'])}; calls={d['calls']}, best={d['best']:.6f}")
        elif args.command == "audit":
            from .audit import audit_run
            print(json.dumps(audit_run(args.directory.resolve()), indent=2))
        else:
            print(write_report(args.directory.resolve()))
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0
