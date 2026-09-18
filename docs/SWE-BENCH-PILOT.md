# Public repository-repair pilot

Status: preparation in progress; no model-generated benchmark results yet.
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

The shipped `repo-solve` snapshot workflow is not yet a full SWE-bench solver.
Prepared-image workspaces, issue-driven retrieval, and benchmark candidate
generation are still required. Repository search currently uses a fixed policy;
no learned repository-controller improvement has been demonstrated.
