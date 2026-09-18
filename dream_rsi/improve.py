from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import statistics

from .engine import OutOfSupport, replay, reward, world_summary
from .policy import Policy, PolicySpec
from .types import World, save_json, stable_seed


POLICY_SCHEMA = {"type": "object", "properties": {
    **{key: {"type": "string"} for key in ("name", "rationale", "priority", "eligible", "batch_size", "width", "depth")},
    "beta": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["name", "rationale", "priority", "eligible", "batch_size", "width", "depth", "beta"], "additionalProperties": False}

EDIT_SCHEMA = {"type": "object", "properties": {"expression": {"type": "string"}, "rationale": {"type": "string"}},
               "required": ["expression", "rationale"], "additionalProperties": False}


def focused_prompt(field: str, current: PolicySpec, best: dict, worlds: list[World], failures: list[dict]) -> str:
    specs = {
        "eligible": ("a boolean deciding whether a branch gets another experiment",
                     "is_root (bool); stagnation (consecutive attempts without improvement); beta (0..1, larger means more patience); last_failed (bool); failures (integer)",
                     "is_root or stagnation < (1 + 2 * beta)",
                     "Stop repeated non-improving refinements, but keep roots and justified repairs eligible. True always spends the full budget."),
        "priority": ("a number ranking eligible branches; larger ranks first",
                     "is_root (bool); anchor (best successful branch score); baseline; global_best; depth (integer); beta (0..1); stagnation",
                     "(anchor - baseline) + beta / (depth + 1)",
                     "Balance productive directions and underexplored directions. Changing ranking alone cannot reduce work when everything stays eligible."),
        "width": ("an integer number of directions to make available BEFORE the next run",
                  "hard_width (upper bound); hard_depth; workers; beta; history_count; last_gain; last_work; plateau_rounds",
                  "hard_width if history_count < 2 else max(workers, int(hard_width * beta))",
                  "Keep enough independent directions to preserve discovery quality; reduce width only when history supports it. Cold start should keep hard_width."),
        "depth": ("an integer maximum number of attempts per direction BEFORE the next run",
                  "hard_width; hard_depth (upper bound); workers; beta; history_count; last_gain; last_work; plateau_rounds",
                  "hard_depth if history_count < 2 else max(2, int(hard_depth * beta))",
                  "Avoid depths that repeatedly waste work, but preserve late improvements. Cold start should keep hard_depth."),
        "batch_size": ("an integer number of independent candidates to run in parallel",
                       "workers (upper bound); legal_count; beta; baseline; global_best; opened; probes; rounds",
                       "min(workers, legal_count)", "Batch useful work rather than serializing it. Zero stops the entire run.")}
    meaning, variables, example, advice = specs[field]
    traces = []
    for w in worlds:
        traces.append({"baseline": round(w.baseline_score, 6), "branches":
                       [[round(n.evaluation.score, 6) if n.evaluation.valid else "invalid" for n in w.nodes if n.branch == b] for b in range(w.branch_count)]})
    return f"""Edit ONE Python expression in an exploration controller: {field}.
This expression returns {meaning}.
Current expression: {getattr(current, field)}
Current measured replay: best score {best['default']['mean_best']:.6f}, mean calls {best['default']['mean_calls']:.2f}, objective {best['selection_score']:.6f}.
Improve the measured quality/work tradeoff using these COMPLETE HISTORICAL branch score sequences: {traces}
{advice}
Allowed variable names ONLY: {variables}.
Allowed Python: numeric literals, + - * /, comparisons, lowercase and/or/not, min, max, int, abs, and conditional x if condition else y.
Syntax example (illustrative, not a validated winning candidate): {example}
Write your own revised expression from the measured feedback. If the current expression is the same as this example, revise it rather than copying it unchanged.
Do not invent variable names. No attributes, file access, branch IDs, hidden scores or absolute score thresholds.
Earlier rejected edits: {failures[-2:]}
Return JSON {{"expression":"YOUR EXPRESSION", "rationale":"explain the change in at most 20 words"}}.
Only edit {field}. The code will be measured in replay and rejected if worse."""


def evaluate_policy(spec: PolicySpec, worlds: list[World], budget: int, cost: float, parallel_bonus: float,
                    betas=(0.2, 0.6, 1.0), objective="paper") -> dict:
    if not worlds:
        raise ValueError("policy evaluation needs at least one completed world")
    evaluations = []
    # Default beta is included explicitly: selection cannot silently deploy a
    # beta that was never evaluated. The sweep is diagnostic under paper scoring.
    for beta in sorted(set((*betas, spec.beta))):
        episodes = []
        for index, world in enumerate(worlds):
            policy = Policy(spec, beta=beta)
            plan = policy.plan_grid(world.hard_branch_count or world.branch_count, world.hard_max_depth or world.max_depth, world.workers,
                                    world.planning_history if world.planning_history is not None else [world_summary(w) for w in worlds[:index]])
            try:
                episode = replay(policy, world, budget, plan)
            except OutOfSupport as exc:
                episodes.append({"world": world.name, "status": "out_of_support", "error": str(exc), "requested_plan": list(plan),
                                 "available_plan": [world.branch_count, world.max_depth]})
                continue
            ceiling = world.best_score
            curve = episode.curve + [episode.best_score] * (budget - len(episode.curve))
            # Normalization belongs ONLY in the evaluator, never policy features.
            if ceiling > world.baseline_score + 1e-12:
                attainment = [max(0.0, min(1.0, (s - world.baseline_score) / (ceiling - world.baseline_score))) for s in curve]
            else:
                attainment = [1.0] * budget
            episodes.append({"world": world.name, "status": "supported", "score": reward(episode, cost, parallel_bonus),
                             "attainment_auc": statistics.mean(attainment),
                             "parallel_penalty": episode.rounds / episode.calls if episode.calls else 0.0,
                             **episode.to_dict()})
        supported = all(e["status"] == "supported" for e in episodes)
        evaluations.append({"beta": beta, "supported": supported,
                            "mean_score": statistics.mean(e["score"] for e in episodes) if supported else None,
                            "mean_calls": statistics.mean(e["calls"] for e in episodes) if supported else None,
                            "mean_best": statistics.mean(e["best_score"] for e in episodes) if supported else None,
                            # Unsupported worlds earn no normalized attainment;
                            # they are never silently omitted from the average.
                            "attainment_auc": statistics.mean(e.get("attainment_auc", 0.0) for e in episodes),
                            "parallel_penalty": statistics.mean(e.get("parallel_penalty", 1.0) for e in episodes), "episodes": episodes})
    default = next(e for e in evaluations if e["beta"] == spec.beta)
    if not default["supported"]:
        raise OutOfSupport("default-beta plan is outside one or more frozen worlds; cannot select this candidate")
    # Two separate objectives: Section 3 and the Appendix B surrogate. Do not
    # pretend their coefficients or scores are interchangeable.
    pareto = statistics.mean(e["attainment_auc"] - 0.05 * e["parallel_penalty"] for e in evaluations)
    return {"policy": spec.to_dict(), "selection_score": default["mean_score"] if objective == "paper" else pareto,
            "objective": objective, "default": {k: v for k, v in default.items() if k != "episodes"},
            "pareto_reward": pareto, "sweep": evaluations}


def compact_feedback(evaluation: dict) -> dict:
    feedback = {k: v for k, v in evaluation.items() if k != "sweep"}
    feedback["sweep"] = [{k: v for k, v in item.items() if k != "episodes"} for item in evaluation["sweep"]]
    default = next(e for e in evaluation["sweep"] if e["beta"] == evaluation["policy"]["beta"])
    feedback["trajectories"] = [{"world": e["world"], "best": e["best_score"], "calls": e["calls"], "stop": e["stop_reason"],
                                "rounds": [{"selected": d["selected"], "best": d["best"], "calls": d["calls"]} for d in e["decisions"]]} for e in default["episodes"]]
    return feedback


def improve(model, incumbent: PolicySpec, worlds: list[World], revisions: int, budget: int, cost: float,
            parallel_bonus: float, seed: int, out: Path, objective: str = "paper", editor: str = "full", feedback: str = "", on_progress=None) -> tuple[PolicySpec, dict]:
    out.mkdir(parents=True, exist_ok=True)
    evaluations = [evaluate_policy(incumbent, worlds, budget, cost, parallel_bonus, objective=objective)]
    save_json(out / "candidate_00.json", evaluations[0])
    (out / "candidate_00.py").write_text(incumbent.source())
    failures = []
    for revision in range(1, revisions + 1):
        best = max(evaluations, key=lambda e: e["selection_score"])
        current = PolicySpec(**best["policy"])
        # The developer may examine completed histories between versions. Its
        # proposed policy cannot access them at decision time.
        branch_patterns = []
        for w in worlds:
            branch_patterns.append({"world": w.name, "baseline": w.baseline_score,
                                    "trajectories": [[{"score": round(n.evaluation.score, 7), "valid": n.evaluation.valid}
                                                      for n in w.nodes if n.branch == b] for b in range(w.branch_count)]})
        prompt = f"""Improve a small executable exploration controller using measured historical replay.
Return ONLY a JSON object matching this schema: {POLICY_SCHEMA}
Each of priority, eligible, batch_size, width, depth is a short PYTHON EXPRESSION string, NOT a function or statement.
Allowed syntax: numbers, booleans, + - * /, comparisons, and/or/not, conditional expressions (x if test else y), min, max, abs, int, round.
No imports, attributes, lists, indexing, lambdas, unknown variables, hidden scores or absolute score targets.

priority and eligible may use these observed-prefix variables:
is_root: True for a new direction; depth: completed attempts in this direction;
anchor: this direction's best successful score (at least baseline);
latest: most recent score; gain: latest score minus previous best;
stagnation: consecutive attempts without improvement; failures: invalid attempts;
last_failed: most recent attempt invalid; successes: valid attempts; remaining: remaining depth.
They may also use beta, baseline, global_best, opened, probes, workers, rounds, legal_count.
batch_size may ONLY use beta, baseline, global_best, opened, probes, workers, rounds, legal_count.
width and depth may ONLY use beta, hard_width, hard_depth, workers, history_count, last_gain, last_work, plateau_rounds.
These last two are grid planning BEFORE an episode; insufficient history should keep the hard caps.
beta is a fixed scalar from 0 to 1 per episode. Larger beta should generally permit more patient exploration.

Selection objective: {objective}. Section 3 paper score = best_score - {cost} * calls + {parallel_bonus} * calls/max(1,rounds).
Appendix surrogate = mean normalized attainment AUC - 0.05 * sequential-rounds/probes, across a beta sweep.
Keep quality while cutting wasted refinements. Batch independent directions. Distinguish invalid proposals from poor valid results.
You can express a NEW strategy, not just edit a number. Avoid hardcoding scores, branch IDs or task answers.
Example of syntax only: priority="(anchor-baseline) + beta/(depth+1)"; eligible="is_root or stagnation < 1 + 3*beta or (last_failed and failures < 2)".
This is an example, not an automatically supplied candidate; justify choices using actual feedback.
Usually batch_size="workers", width="hard_width", depth="hard_depth" are sensible unless evidence supports a change.

Current best policy: {current.to_dict()}
Measured feedback: {[compact_feedback(e) for e in evaluations]}
Completed branch outcomes: {branch_patterns}
Rejected revisions: {failures}
Propose revision {revision}; keep rationale under 35 words. Output JSON only."""
        try:
            if editor == "focused":
                fields = ("eligible", "priority", "width", "eligible", "depth", "batch_size")
                field = fields[(len(worlds) + revision - 2) % len(fields)]
                prompt = focused_prompt(field, current, best, worlds, failures)
                if feedback:
                    prompt += "\nPrevious completed promotion checks (new validation seeds will be used): " + feedback
                result = model.generate(prompt, EDIT_SCHEMA, stable_seed(seed, "policy", revision), "policy", f"{out.name}-revision-{revision:02d}", max_tokens=240)
                proposed = replace(current, **{field: result["expression"]}, name=f"{out.name}-edit-{revision:02d}-{field}", rationale=result["rationale"])
            else:
                result = model.generate(prompt, POLICY_SCHEMA, stable_seed(seed, "policy", revision), "policy", f"{out.name}-revision-{revision:02d}", max_tokens=600)
                proposed = PolicySpec(**result)
            Policy(proposed)  # Validate syntax before any evaluation.
            evaluation = evaluate_policy(proposed, worlds, budget, cost, parallel_bonus, objective=objective)
            evaluations.append(evaluation)
            save_json(out / f"candidate_{revision:02d}.json", evaluation)
            (out / f"candidate_{revision:02d}.py").write_text(proposed.source())
        except (ValueError, TypeError, SyntaxError, KeyError) as exc:
            failure = {"revision": revision, "error": str(exc)}
            failures.append(failure)
            save_json(out / f"candidate_{revision:02d}_rejected.json", failure)
        if on_progress:
            on_progress({"revision": revision, "total": revisions, "valid": len(evaluations)-1, "rejected": len(failures)})
    # Stable tie: incumbent retained. No cherry-picking on future online outcomes.
    selected = max(evaluations, key=lambda e: e["selection_score"])
    spec = PolicySpec(**selected["policy"])
    summary = {"selected": spec.to_dict(), "before": evaluations[0]["selection_score"], "after": selected["selection_score"],
               "valid_revisions": len(evaluations) - 1, "rejected_revisions": failures,
               "replay_evaluations": sum(len(e["sweep"]) * len(worlds) for e in evaluations),
               "offline_discovery_calls": 0, "objective": objective, "editor": editor}
    save_json(out / "selection.json", summary)
    (out / "selected_policy.py").write_text(spec.source())
    return spec, summary
