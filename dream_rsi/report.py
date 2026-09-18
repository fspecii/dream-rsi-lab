from pathlib import Path
import json


def write_report(directory: Path) -> Path:
    result = json.loads((directory / "results.json").read_text())
    comparison = result["comparison"]
    status = ("Matched or exceeded fixed exploration on every fresh pair while using fewer discovery calls."
              if comparison["demonstrated_equal_or_better_quality_with_fewer_calls"] else
              "The fresh evaluation did not demonstrate equal-or-better quality on every pair with fewer calls.")
    lines = ["# Dream-RSI small-model experiment", "", status, "",
             "This is an independent, constrained implementation of the paper's mechanism, not the official code or a replication of all its benchmarks.", "",
             f"Model: **{result['config']['model']}**. Model digest: `{result['model_metadata'].get('digest', 'unknown')}`.",
             f"Policy developer: **{result['config'].get('policy_model') or result['config']['model']}** (also fixed; no training).",
             f"Task: exact sum–difference ratio, integer sets of 4–20 distinct elements in [0,63]. No model-weight updates.", "",
             "## Fresh evaluation", "", "The final controller was frozen before these runs. Both arms received the same training history and initial set per seed. Holdout results were never fed back to the policy developer.", "",
             "| Pair | Fixed score | Dream score | Fixed calls | Dream calls |",
             "|---|---:|---:|---:|---:|"]
    for index, pair in enumerate(result["holdouts"]):
        lines.append(f"| {index+1} | {pair['fixed']['best']:.6f} | {pair['dream']['best']:.6f} | {pair['fixed']['calls']} | {pair['dream']['calls']} |")
    lines += ["", f"Mean score difference (Dream − fixed): **{comparison['mean_quality_difference']:.6f}**.",
              f"Descriptive paired bootstrap 95% interval: {comparison['quality_difference_bootstrap_95']}. With {comparison['pairs']} pairs this is exploratory, not strong statistical evidence.",
              f"Discovery-call reduction: **{100 * comparison['call_reduction_fraction']:.1f}%**.", "",
              "## Recursive training", "", "| Cycle | Dream score | Dream calls | Fixed score | Fixed calls | Replay before | Replay after |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row, selection in zip(result["training"], result["selections"]):
        lines.append(f"| {row['cycle']+1} | {row['dream']['best']:.6f} | {row['dream']['calls']} | {row['fixed']['best']:.6f} | {row['fixed']['calls']} | {selection['before']:.6f} | {selection['after']:.6f} |")
    lines += ["", "Cycle 1 is one shared bootstrap rollout, counted logically in both arms but executed once. Replay scores are comparable only within a cycle's fixed pool.", "",
              "## Actual model usage", "", "| Role | Calls | Input tokens | Output tokens | Summed request seconds |", "|---|---:|---:|---:|---:|"]
    for role, usage in result["usage"].items():
        lines.append(f"| {role} | {usage['calls']} | {usage['input_tokens']} | {usage['output_tokens']} | {usage['request_seconds']:.1f} |")
    if any(result.get("imported_training_calls", {}).values()):
        lines += ["", f"Cumulative usage includes previously executed training calls imported from the parent: {result['imported_training_calls']}. They were not executed again. Old holdout results were excluded."]
    lines += ["", f"This invocation's elapsed wall time: {result['wall_seconds']:.1f} seconds. Request time can overlap across workers.",
              "Policy-generation calls are included above; replay makes zero discovery-model or task-evaluator calls. Logical batches do not guarantee GPU inference concurrency in Ollama.", "",
              "## Selected executable policy", "", "```python", (directory / "frozen_policy.py").read_text().rstrip(), "```", "",
              "## Limits", "", "- Frozen replay covers recorded continuations only; it cannot simulate new outcomes or fully model changed cross-branch context.",
              "- The discovery model proposes literal integer constructions; it is not an unrestricted code-generating agent. The controller writes bounded Python expressions.",
              "- This bounded CPU task does not reproduce the paper's Lasso, GPU kernel, or other mathematical benchmark results.",
              "- Small stochastic local-model runs can differ even with identical seeds. Raw requests, responses, failures, and model digest are retained.",
              "- Improvements in a selected replay objective alone do not prove online improvement; the fresh table is the relevant test.", "",
              "## Inspect the evidence", "", "- `config.json`: fixed experiment settings and model identity.",
              "- `model_calls/`: all prompts, raw responses, seeds, token counts, and durations.",
              "- `worlds/*/world.json`: discovery trees and every decision's revealed-prefix features.",
              "- `worlds/*/attempts/*/program.py`: executable construction artifacts.",
              "- `policies/cycle-*/`: candidate source, beta sweeps, replay decisions, rejection logs, and selection.",
              "- `frozen_policy.json` / `.py`: policy selected before fresh testing.", ""]
    path = directory / "REPORT.md"
    path.write_text("\n".join(lines))
    return path
