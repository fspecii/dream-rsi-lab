# Measured small-model experiments

The math experiments below used local **Qwen 3.5 0.8B** for both construction
generation and controller development, with no weight updates. Its recorded digest
is `f3817196d142eaf72ce79dfebe53dcb20bd21da87ce13e138a8f8e10a866b3a4`.
Task evaluations compute the exact sum–difference ratio on bounded integer sets.

## First attempt: broad controller editing

`runs/qwen08-demo-v1` ran three recursive cycles and four fresh pairs. The model
produced valid controller variations but mainly changed branch ranking while
leaving every branch eligible. No variation improved the selected replay objective.
The incumbent stayed in place. Both fresh arms used 64 discovery calls and reached
score 1.0 on all four pairs: **no demonstrated efficiency improvement**.

This unsuccessful run is retained. Its independent evidence audit passed; a
correctly functioning loop is not guaranteed to find a better policy.

## Second attempt: focused expression edits

`runs/qwen08-focused-v2` used a new training seed (2027), three cycles, four proposed
edits per cycle, and six fresh paired episodes. The small model edited one
controller expression at a time. Prompts included syntax examples and measured
training feedback; therefore this is scaffolded code editing, not unconstrained
algorithm invention. No fresh outcome was used for policy selection.

The selected code reduced the next grid after two completed histories:

```python
width = hard_width if history_count < 2 else max(workers, int(hard_width * beta))
depth = hard_depth if history_count < 2 else max(1, int(hard_depth * beta))
```

At the fixed default beta of 0.6, a 4×4 grid becomes 2×2. The selected policy kept
the best replay score while reducing discovery work. Its mean paper-objective
score on the third frozen pool increased from **0.985 to 0.989**.

| Fresh evaluation | Fixed exploration | Replay-selected policy |
|---|---:|---:|
| Paired episodes | 6 | 6 |
| Total discovery-model calls | 96 | 24 |
| Mean best exact task score | 1.0 | 1.0 |
| Pairs matching or exceeding fixed quality | — | 6 / 6 |

That is **75% fewer discovery calls on these six fresh pairs**, with matched final
scores. This is an exploratory demonstration, not a statistical guarantee or a
replication of the paper's large-scale benchmarks. The result is easy to interpret
because the tiny model largely reaches a simple plateau at 1.0. Known nontrivial
sets exceed that score; this experiment does not claim a new mathematical result.

The run made **200 discovery-model calls and 12 policy-development calls** in total,
including training controls and fresh evaluations. Policy inference is not free;
the raw usage files also retain token counts and request durations. Replay itself
does not invoke either the discovery model or the task evaluator.

Full raw evidence, source snapshots, plots and readable reports were retained in
the maintainer’s local run directories; these larger math archives are not included
in this repository. A small real replay sample is included in `examples/` so it
can run without a model or those larger logs.

## Fourth recursive cycle: replay improvement did not generalize

`runs/qwen08-recursive-v3` continued the second run's **training evidence only**.
Old holdouts were not imported. The learned 2×2 controller drove a new real online
cycle, reaching score **1.0 in 4 calls** versus **16 calls** for fixed exploration.
That new, smaller discovery tree was then added to the replay pool. This exercises
the complete loop after an actual policy upgrade, including irregular replay
support and unsupported high-beta grid plans.

Replay next selected a more aggressive eligibility expression:

```python
is_root or (stagnation < (1 + beta * is_root))
```

It can abandon a branch after a single non-improving root. Its mean replay
objective increased from **0.991 to 0.994725**, but four new fresh paired episodes
showed the limitation:

| Fresh evaluation | Fixed exploration | New aggressive policy |
|---|---:|---:|
| Discovery calls | 64 | 12 |
| Mean best task score | 1.0 | 0.963911 |
| Pairs matching fixed quality | — | 2 / 4 |

This is a **regression in fresh solution quality**, despite further replay
improvement. It is not counted as successful equal-quality cost reduction. The
earlier six-pair result is still valid, but it does not imply recursive improvements
will keep generalizing. The shipped replay example retains the earlier controller;
the later candidate and its unfavorable evidence remain in their own run.

This result makes the limits concrete: replay is restricted to historical outcomes,
the small controller developer can over-prune, and the framework does not claim
that every selected code revision is safe to deploy without fresh validation.

To reproduce the continuation (after the preceding focused run):

```bash
python3 -m dream_rsi run --output runs/reproduce-continuation \
  --continue-from runs/reproduce-focused --seed 2027 --cycles 4 \
  --branches 4 --depth 4 --budget 16 --revisions 4 --holdout-seeds 4
```

## Reproduce / verify

```bash
python3 -m dream_rsi run --output runs/reproduce-focused \
  --seed 2027 --cycles 3 --branches 4 --depth 4 --budget 16 \
  --revisions 4 --holdout-seeds 6 --policy-editor focused

python3 -m dream_rsi audit runs/qwen08-focused-v2
```

Exact reruns can differ because local model inference is not guaranteed to be
bitwise deterministic across server versions, scheduling and hardware. The
archived traces can be replayed deterministically without model inference.

## Persistent lab validation (2026-09-18)

The browser workflow was exercised with real `qwen3.5:0.8b` inference in workspace
`bd2a83a9b855`, including pause, server restart, and resume during fresh validation.
Three cycles completed:

- Cycle 1: replay improved slightly, but the candidate used 64 discovery calls
  against the incumbent's 64 across four fresh pairs. Both scored 1.0 throughout.
  The lab rejected the candidate because it did not improve the fresh result.
- Cycle 2: the model edited search depth. Four fresh pairs all reached score 1.0
  for both policies; candidate calls were 32 versus 64. The lab promoted v01,
  a **50% reduction in discovery calls** on these checks.
- Cycle 3: collected experiments using v01 and retained it after replay found
  no further improvement.

Total overhead-inclusive usage was 276 model calls: 264 discovery and 12 policy
editing calls. The 50% figure concerns cycle 2's paired discovery episodes, not
net savings after training and validation overhead. Nineteen completed worlds were
independently checked for exact scores, model-output provenance, and identical
online/replay decisions. Completed steps were not repeated after restart.

The compact measured record is in `examples/lab-validation-summary.json`. Full
requests, responses, candidate evaluations, state, and discovery worlds remain in
`.dream-rsi/sessions/bd2a83a9b855/` on this machine. A fresh installation starts with an empty workspace list and the bundled recorded replay. These small-sample results do not
guarantee future improvements.

## Developer workflow checks (2026-09-18)

These experiments use the included twelve-problem synthetic Python suite. Four
problems belong to each of train, validation, and test. They test function-level
repair and generation, not repository editing or industrial developer productivity.
All execution used the same local Docker interpreter image:
`sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea`.

### Initial repair observations

| Model | Problem | Calls | Selected visible score | Selected private score |
|---|---|---:|---:|---:|
| Qwen 3.5 0.8B | batch-items | 4 | 50% | 50% |
| Gemma 3 4B | batch-items | 4 | 100% | 100% |
| Gemma 3 4B | query-values | 2 | 50% | 50% |
| Qwen 2.5 Coder 7B | query-values | 2 | 50% | 50% |

These are development observations with different configurations, not a controlled
ranking of models. Version 1 of the coding prompt requested source and a rationale;
verbose rationales sometimes exhausted the response budget. Version 2 requests only
source. The query trials and all Qwen Coder workspace/benchmark calls use version 2.
The default Gemma example demonstrates one successful repair, not broad reliability.

### Persistent controller improvement

Gemma completed four cycles with **64 calls** (52 discovery, 12 policy edits). No
controller was promoted. Cheaper candidates lost private-test quality, and one
cycle found no replay improvement. Negative outcomes remain in the archive.

Qwen 2.5 Coder 7B completed three cycles with **33 calls** (24 discovery, 9 policy
edits). The first two cycles retained the current policy. The third proposed
halving search width after two histories. Across the two fresh validation problems,
it used four discovery calls against eight for fixed search and matched private
scores. However, both policies scored zero on query-values. The positive-quality
requirement rejected the candidate, so **no coding-policy improvement was accepted**.

No final test problems were used in these cycles. Validation problems were reused
adaptively, so they cannot substitute for an untouched final test set.

The full coding records, including failed repairs and rejected proposals, are in
[the evidence archive](../examples/evidence/README.md). Historical math efficiency
results above must not be presented as coding efficiency results.

### Reserved test results

The frozen Qwen Coder workspace was evaluated once on all four reserved problems,
with two directions and two attempts per direction. Since no edit was accepted,
both arms use v00. This is a fixed-policy reproducibility check, **not evidence of
learned efficiency**. Both arms produced the same private scores:

| Test problem | Private tests passed | Discovery calls per arm |
|---|---:|---:|
| flatten-config | 2 / 3 | 4 |
| pagination | 3 / 4 | 4 |
| run-length | 3 / 3 | 4 |
| path-normalize | 4 / 4 | 4 |

**Two of four problems were fully solved**, with zero call reduction. Visible-test
success did not ensure private-test success. The benchmark made 32 discovery calls
in total, used 15,410 input and 3,290 output tokens, and took about 213 seconds on
the local machine. The preceding Qwen Coder training cost 33 additional calls;
those are not included in the paired discovery-call counts. Runtime and caching
make latency hardware-dependent.

See the [full benchmark report](../examples/evidence/qwen-coder-reserved/REPORT.md)
and [machine-readable results](../examples/evidence/qwen-coder-reserved/result.json).
To independently rerun all visible and private evaluations without model inference:

```bash
python3 scripts/verify_code_benchmark.py examples/evidence/qwen-coder-reserved
```

Install this package first and make the recorded Docker image available. The verifier
checks source provenance, test snapshots, visible scores, replay decisions, selected
artifacts, private scores, call counts, and headline totals. It executes generated
source only through the constrained Docker runner.

## Multi-file repository repair development checks

The repository runner was exercised on a synthetic fulfilment project with two
editable modules and seven project tests. Local Qwen 2.5 Coder 7B produced a
passing repair in the initial three-call trial. After adding partial-credit scoring,
a three-call trial and a six-call trial each retained a 5/7 partial repair and
correctly returned an incomplete status. All three selected patches were rerun
without model inference, checking the snapshot, source provenance, exported diff,
and final test score. The original source checkout stayed unchanged.

These development trials use visible tests and different scoring configurations.
They are not a controlled benchmark, a reliability estimate, or evidence of learned
repository-controller improvement. [Raw positive and negative evidence](../examples/repository/evidence/README.md) is included.

The next evaluation target is a public repository-repair benchmark. No public benchmark result is claimed yet.
