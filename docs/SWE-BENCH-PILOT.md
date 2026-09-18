# Public repository-repair pilot

Status: two of three registered baseline attempts are complete. The Django policy
comparison is complete; Matplotlib environment recovery is in progress.
This three-task engineering pilot cannot establish benchmark-wide performance,
controller efficiency, or industry impact. Tasks used to develop the solver are
no longer untouched evaluation tasks.

## Registered selection

Use the official [SWE-bench harness](https://github.com/SWE-bench/SWE-bench)
at `02e7a74ffd0b707aab73d203fe87bdc7c76afc8e` (5.0.2) and
[task repository](https://github.com/SWE-bench/swe-bench-tasks) at
`3d07b464b7b311a0cbfb5ed5b2d8a3b96f84a33d`.

Before candidate inference, filter Verified/test membership, exclude environment
control `sympy__sympy-20590`, sort the remaining 499 instances by ascending
SHA256 of `dream-rsi-pilot-20260918:` plus instance ID, and choose the first three
distinct repositories. The registered tasks are:

| Instance | Base commit |
| --- | --- |
| pydata__xarray-6461 | 851dadeb0338403e5021c3fbe80cbc9127ee672d |
| django__django-11163 | e6588aa4e793b7f56f4cadbfa155b581e0efc59a |
| matplotlib__matplotlib-26291 | fa68f46289adf4a8a4bc7ba97ded8258ec9d079c |

Environment failures remain in the pilot report; do not substitute easier tasks.
Record the exact model digest, image IDs, implementation hashes, inference budget,
tool limits, selection rule, and stopping rule before candidate inference.

## Input and scoring separation

`scripts/prepare_swebench_inputs.py` uses the official loader and emits only
`instance_id`, `repo`, `base_commit`, `image`, and `problem_statement`. It verifies
the clean task-repository commit, exact registered task set, and registered
metadata. Unknown columns are excluded by default. Existing output is never
overwritten. The canonical public-input digest for this pilot is
`60361d69d9872efc87ec711db3d2ee03e9a3b0f322b41b8b9f4b5820372f2c8b`.

Run preparation with the official harness Python environment and this checkout
on `PYTHONPATH`, supplying `--task-repo`, `--plan`, and `--output` paths.
The plan schema is demonstrated in `examples/benchmarks/swebench-pilot-plan.json`.
Candidate generation must consume the exported inputs, not the full task rows.
Do not mount the task repository or evaluator artifacts into candidate containers.

Repository retrieval must start from the public issue and base checkout. Do not
derive editable paths from reference patches, evaluation patches, hidden test
names, or solution links. Public issue text is preserved verbatim; some issues,
including the selected Django issue, already suggest a fix. Report this limitation
and do not treat such a task as evidence of independent bug diagnosis. Do not
follow links to later fixes. This separation also cannot prove that a pretrained
model has never seen these public projects or issues.

Use existing project tests and issue-derived reproducers during discovery. Run the
official evaluator only on frozen predictions, under unique run IDs. Keep official
test outcomes out of subsequent search for that run. Green existing tests alone
do not establish that an issue is fixed. Report resolved, unresolved, empty patch,
infrastructure failure, and incomplete outcomes separately, with the full selected
task count visible. Preserve failed attempts and model-call cost.

## Environment positive control

On 2026-09-18, the official reference patch for the excluded SymPy control resolved
1/1 instances, with zero infrastructure errors. This validates the local harness
path; it is not a model repair result. The first build failed with insufficient
memory in a 3 GB Colima VM. Retrying in an 8 GB VM succeeded, using the official
linux/amd64 image build under emulation on an ARM host. Preserve both outcomes.

## Experimental candidate runner

The Django baseline needed a separate compatibility retry. Its prepared image
uses Python 3.6; the original file driver failed to decode a non-ASCII command and
also depended on a newer pathlib API. The invalid attempt was interrupted after
18 completed requests and one request in flight. Its logs and recorded costs are
preserved, but it is not a model-quality result. The corrected adapter passed the
full fixture workflow inside that same Python 3.6 image. Remaining baseline runs
use the published `benchmark-baseline-compat` branch, preserving the original
search policy with these infrastructure fixes. See the archived interruption note
for the old runner's inaccurate final status and incomplete in-flight token cost.

The first xarray attempt exhausted all 24 calls without producing a patch. Its
three reads and 21 replacements all targeted nonexistent files and failed. The
official harness classified the submitted prediction as **empty**, with zero
resolved instances; it did not execute tests for that empty submission. Recorded
cost was 35,808 input tokens, 1,355 output tokens, and 275.9 seconds of model-request
time. This is a failed candidate search, not an infrastructure failure or a full
three-task benchmark score. The corrected Django baseline also exhausted 24 calls
with an empty patch: all 14 reads, six replacements, and four shell actions failed.
Its recorded cost was 29,400 input tokens, 1,014 output tokens, and 177.5 seconds of
model-request time, in addition to the separate interrupted infrastructure attempt.
The official harness classified this submission as empty with zero resolutions.
Matplotlib remains pending. Thus neither completed baseline task was resolved.

An earlier setup attempt stopped with zero model calls because the prepared image
retained its environment-setup revision. The runner was corrected to reset to the
registered base before inference. Both records are preserved in
[the evidence directory](../examples/benchmarks/evidence/README.md).

After exporting public inputs and building the selected official image locally:

```bash
python3 -m dream_rsi.benchmark_solver \
  --inputs /path/to/pilot-public-inputs.json \
  --instance pydata__xarray-6461 \
  --output runs/swebench-xarray \
  --model qwen2.5-coder:7b --steps 24 --seed 2027
```

The runner validates the input digest, verifies the image's base checkout, removes
later Git history/remotes, and gives the model bounded `run`, `read`, `replace`, and
`finish` actions. Search and editable-file selection come from model actions on
the public checkout. It saves runtime/model/implementation identifiers before
inference and records every call, tool observation, and current patch. The fixed
policy submits the current patch at finish or budget exhaustion. It does not
optimize against official test outcomes. An infrastructure failure is recorded
without silently emitting a valid prediction; the latest saved patch remains
available for diagnosis.

The output `prediction.jsonl` uses the official harness prediction format. Evaluate
it separately, with a new run ID for every attempt:

```bash
swebench eval verified --predictions /path/to/run/prediction.jsonl \
  --run-id unique-candidate-run --task-repo /path/to/swe-bench-tasks -j 1
```

Check recorded actions, model costs, implementation snapshots, and prediction
consistency without inference using `python3 -m dream_rsi.benchmark_audit RUN_DIR`.
This audit does not execute the patch or replace official resolution scoring.

Default bounds are 24 model calls, 4,096 output tokens per call, 60 seconds per
container command, 2 GB container memory, 2 CPUs, and 128 processes. These are
engineering defaults, not tuned performance claims. The writable container runs
as root with capabilities dropped, no network or host mounts; see
[security scope](../SECURITY.md). Container logs are disabled; tool output is
captured and bounded by the runner. Preserve all failed and incomplete runs.

Real Docker fixture tests cover repair/export, original-image preservation,
history removal, path rejection, timeout/overflow cleanup, and the complete
model-action-to-prediction workflow. Enable these with
`DREAM_TEST_PREPARED_BASE` naming an available image containing Git and Python.

The shipped `repo-solve` snapshot workflow remains separate. Default repository
workflows still use fixed policies; no learned repository-controller
improvement has been demonstrated. The incomplete pilot does not establish useful
benchmark performance.

## Unvalidated controller proposal

The model has proposed one bounded controller change from the xarray training
trace: read a file successfully before editing it, avoid exact failed tool actions,
and retain four recent observations. It left mandatory initial search disabled.
The proposal consumed one additional call, 5,311 input tokens, 186 output tokens,
and 35.7 seconds. Its rationale is model-generated and remains a hypothesis.

The proposal and its [validation plan](../examples/benchmarks/evidence/repository-policy-proposal-20260918/validation-plan.json)
were recorded before inspecting either validation baseline outcome. Django baseline
inference had already started. Django and Matplotlib are exploratory validation
tasks; they cannot subsequently be described as independent final tests.

The candidate must preserve each baseline resolution, resolve at least one task,
and either improve total resolutions or reduce discovery calls by at least 10%
at preserved quality. Any missing or infrastructure-failed run blocks a decision.
Proposal and validation overhead remains part of total cost. Passing this small
gate would still require a new independent final sample before stronger claims or
changing the default policy. No promotion has occurred.

The Django candidate also produced an empty patch after 24 calls. It made 14
successful file reads but did not find the relevant implementation. Recorded
candidate cost was 53,294 input tokens, 1,089 output tokens, and 333.1 seconds of
model-request time, versus 29,400 / 1,014 / 177.5 seconds for the valid baseline.
The official harness recorded both predictions as empty. There is no improvement
on this task. The full gate remains incomplete until the registered Matplotlib
pair is available; no task is dropped from the comparison.

Matplotlib's local image build failed with a GCC internal compiler segmentation
fault while compiling bundled FreeType under amd64 emulation. No model call ran.
Recovery uses the official registry image, pinned to its amd64 manifest digest,
and retains the same task. This is infrastructure evidence, not a model failure.

`python3 -m dream_rsi.repository_validation` checks the recorded proposal,
candidate implementation hashes, budgets, matching input/image/model identities,
candidate audits, and supplied official outcomes before applying the gate. It
reports missing tasks explicitly and never promotes a policy automatically. Its
`--locations` JSON maps each registered instance to `baseline` and `candidate`
objects containing `run` and `report` paths. Supply `--plan`, `--proposal`, and an
optional new `--output` file. Official report hashes identify the supplied reports;
they are not independently signed attestations or a replacement for the harness.

Generate a proposal with `python3 -m dream_rsi.repository_policy --training-run
RUN_DIR --output NEW_DIR`. Experimental candidate runs may specify
`--policy /path/to/proposal.json`. Policy controls affect tool selection and bounded
history; they cannot modify the model, task, test oracle, or call budget. A rejected
precondition can become valid after a successful read; only executed tool failures
are considered by the exact-action repeat check. The default runner remains fixed.
