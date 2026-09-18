# A small, runnable Dream-RSI experiment

This is an independent implementation based on the paper in the [original Dream-RSI paper](https://github.com/zhengkid/Dream-RSI/blob/main/papers/Dream-RSI.pdf).
The upstream repository did not contain the framework when this work began. The
original README and paper describe the authors' system; this document describes
the implementation in this checkout.

For an immediate no-model walkthrough, run the [recorded replay example](examples/README.md).
For measured fresh results—including an unsuccessful first attempt—see
[experiment notes](docs/experiments.md).

The demonstration uses a fixed **Qwen 3.5 0.8B** model through local Ollama. It does
not train a new language model or update its weights: the paper's self-improvement
happens in the exploration controller. A model generates candidate mathematical
constructions; the same fixed model separately writes new controller expressions.

## Use the local app

Run `python3 -m dream_rsi lab --open` for the browser interface. It includes an offline
recorded replay and persistent math workspaces with start, pause, resume, fresh
validation, policy history, and source downloads. See [LAB.md](LAB.md).
The lab adds a stricter fresh-validation promotion gate than the research runner below.

## Run it

Requirements: Python 3.11 or newer and a running Ollama with `qwen3.5:0.8b` installed.
The Python framework uses only the standard library. Run these from this directory:

```bash
python3 -m dream_rsi doctor
python3 -m unittest discover -s tests -v
python3 -m dream_rsi run --output runs/my-demo
```

The default experiment uses three recursive cycles, four directions, up to four
attempts per direction, two logical workers, three proposed policy revisions per
cycle, and four fresh paired evaluations. The first training trajectory is shared
exactly by Dream-RSI and fixed exploration. All later live proposals use actual
model inference and the exact task evaluator. No synthetic scores are substituted.

For a smaller pipeline check (too small for persuasive performance evidence):

```bash
python3 -m dream_rsi run --output runs/quick-check \
  --cycles 2 --branches 2 --depth 3 --budget 6 \
  --revisions 2 --holdout-seeds 2
```

Use another installed model with `--model gemma3:4b`. Use `--base-url` to select a
different Ollama server. Requests use Ollama's documented [chat API](https://docs.ollama.com/api/chat)
and [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).
The CLI never downloads a model or silently falls back to a larger/paid model.

If the 0.8B model cannot write useful controller code, keep it for discovery and
explicitly use the installed 4B model for policy development:

```bash
python3 -m dream_rsi run --output runs/mixed-small-models \
  --model qwen3.5:0.8b --policy-model gemma3:4b
```

Both models remain fixed throughout training and evaluation; their identities and
separate costs are recorded. There is no hidden fallback. Each run also saves the
framework source and SHA-256 hashes, plus the holdout seed plan before execution.

Each run needs a new output directory. Failures preserve model logs and completed
worlds; the CLI does not claim an interrupted experiment was completed.

Continue from saved training evidence without redoing earlier inference:

```bash
python3 -m dream_rsi run --output runs/continued \
  --continue-from runs/my-demo --cycles 4
```

Preserve the original seed, model, task caps, workers and reward coefficients when
continuing (pass the same flags if they differed from defaults). Only training
worlds, controller revisions and their model calls are inherited. Previous
holdouts are excluded, and the continuation predeclares new holdout seeds. Usage
separately identifies imported training calls so they are not mistaken for new work.

## What happens

```mermaid
flowchart LR
    P[Current controller code] --> O[Online construction agent]
    O --> E[Exact mathematical evaluation]
    E --> T[Recorded discovery trees]
    T --> R[Frozen replay pool]
    R --> D[Model proposes revised controller code]
    D --> S[Evaluate candidates in replay]
    S --> B[Select best including incumbent]
    B --> P
    B --> H[Freeze and test on fresh episodes]
```

The online agent constructs a finite integer set A. The fixed evaluator calculates:

```text
sumset     = {a + b : a, b in A}
difference = {a - b : a, b in A}
score      = log(|sumset| / |A|) / log(|difference| / |A|)
```

Higher is better. The demo restricts A to 4–20 distinct integers in [0,63]. This
keeps evaluations tiny while retaining the paper's sum–difference objective.
Arithmetic progressions score 1; some nontrivial constructions exceed 1.
The evaluator rejects duplicates and invalid values. It never trusts a model's
self-reported score or rationale.

Each attempt is an executable literal-construction `program.py`, its proposal,
parent identifier, seed, measured score, and diagnostics. A failed attempt retains
the parent's artifact for possible repair but records an invalid result, never a
successful evaluation. Earlier successful branch scores remain visible.

The controller sees only revealed results. Its executable expressions decide:

- whether each new direction or branch frontier remains eligible;
- which eligible branches have priority;
- how many independent attempts to batch;
- the next episode's available width and depth;
- how a fixed per-episode exploration intensity `beta` affects those decisions.

The default `--policy-editor focused` asks the small model to revise one expression
at a time, rotating among stopping, ranking and grid planning. The rest of the
incumbent is preserved. Prompts contain syntax examples, so this is scaffolded code
editing, not unconstrained invention. Every proposed change still has to improve
the measured replay objective to be selected. `--policy-editor full` asks the model
to rewrite the entire expression program and its default beta in one response.

Controllers use a bounded Python-expression language, interpreted through an AST
allowlist. They cannot access files, network, trace objects, future scores, or run
arbitrary Python. Their exported `.py` representation is readable executable code;
the runner uses the equivalent bounded interpreter. See [architecture](docs/architecture.md).

Replay reads recorded nodes instead of calling the model or task evaluator. Each
policy/world/beta evaluation resets its revealed prefix. The selected candidate
must beat or tie the incumbent on the same frozen pool; ties keep the incumbent.
New live experience expands the next cycle's pool.

## Scoring and fair comparisons

Default selection implements the main paper's Section 3 objective:

```text
best_score - cost * discovery_calls
           + parallel_bonus * discovery_calls / max(1, decision_rounds)
```

Default coefficients are `cost=0.001` and `parallel_bonus=0.0005`, exposed as CLI
flags. These are demo choices, not coefficients recovered from released official code.

The appendix describes a different evaluator based on attainment/work curves and
parallel penalties. `--objective pareto` selects a documented approximation:
mean normalized attainment AUC over a beta sweep, minus 0.05 times the mean
rounds/probes penalty. It is not claimed to reproduce the unreleased evaluator.
The beta sweep is always logged. The default beta is evaluated explicitly.

After training, the final controller is frozen. Four fresh paired episodes use
different seeds from training. Both arms get the **same frozen training history**
and the same initial set per seed. No holdout outcome goes into policy development,
another holdout's prompt, or the selection rule. Execution order alternates.

The report distinguishes discovery-call savings from total model usage, including
all policy-development calls. A local inference server may serialize requests:
logical batching is not evidence of a measured wall-clock parallel speedup.

## Inspect and replay

A completed run writes `REPORT.md`, `results.json`, source for the selected policy,
and all underlying evidence. The raw experiment directories are intentionally
git-ignored because logs grow with every model call.

```text
runs/my-demo/
  config.json                  model metadata and experiment settings
  model_calls/*.json           exact prompts, responses, seeds and token counts
  worlds/*/world.json          complete recorded trees and decision diagnostics
  worlds/*/attempts/*/         executable construction + proposal + evaluation
  policies/cycle-*/            candidate source, replay sweeps, selection and failures
  frozen_policy.json / .py     controller frozen before fresh evaluation
  holdouts.json                fresh paired online results
  usage.json                  actual discovery and policy model usage
  results.json / REPORT.md     result summary and readable interpretation
```

Replay does not need a running model:

```bash
python3 -m dream_rsi replay \
  --world runs/my-demo/worlds/train-00-dream/world.json \
  --policy runs/my-demo/frozen_policy.json --budget 16
python3 -m dream_rsi report runs/my-demo
python3 -m dream_rsi inspect runs/my-demo/worlds/train-00-dream/world.json
python3 -m dream_rsi audit runs/my-demo
```

The audit independently recomputes exact mathematical scores, online/replay
decisions, every candidate's selection score, the fresh comparison, model usage,
and source snapshot hashes. It does not merely trust the summary JSON.

An optional plotting script produces a PNG and SVG (Matplotlib is only needed for
this figure, not the framework):

```bash
uv run --with matplotlib python scripts/plot_run.py runs/my-demo
```

## What this establishes—and what it does not

The goal is a real, small-model demonstration of recursive improvement at the
exploration layer: collect, replay, rewrite, select, redeploy, then test fresh.
Whether it improves depends on the measured run. A selected replay score is not
proof of better fresh performance, and the report says so when the fresh comparison
does not demonstrate a benefit.

The demo does **not** reproduce the reported Lasso runtimes, GPU kernel gains,
large mathematical constructions, or all eight benchmarks. Its discovery artifacts
are literal integer constructions rather than arbitrary solver programs, and its
controllers have a restricted expression representation. Matching the original
benchmarks would require those task integrations, a stronger coding agent,
appropriate hardware, and much larger experiments. See the explicit
[paper-to-implementation mapping](docs/architecture.md#paper-fidelity).
