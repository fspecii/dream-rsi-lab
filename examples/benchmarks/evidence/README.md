# SWE-bench pilot evidence

These are engineering-pilot results, not a benchmark-wide score. The three-task
fixed baseline is complete at zero resolutions; the controller comparison is also
complete and rejected.
The [registered protocol](../../../docs/SWE-BENCH-PILOT.md) explains selection,
input separation, environment preparation, and limitations.

`swebench-pilot-xarray-20260918` records a setup failure before inference: the
prepared image retained a different environment-setup revision. Zero model calls
were made. Initialization was corrected to reset to the registered base commit.

`swebench-pilot-xarray-base-retry-20260918` contains the frozen 24-call model run:
raw requests/responses, tool observations, implementation snapshots, model/image
metadata, the empty patch, and official-format prediction. It exhausted the budget
while repeatedly using nonexistent paths. All 24 tool actions failed.

`xarray-official-results.json` is the official harness report from unique run
`dream-lab-pilot-xarray-fixed-20260918`: one submitted instance, one empty patch,
zero resolved. Empty patches are not executed, so this is not a test-run failure.
`xarray-candidate-audit.json` independently summarizes saved-record consistency and
cost. It does not establish patch correctness.

`swebench-pilot-django-compat-retry-20260918` is the valid Django baseline retry
using the Python 3.6-compatible adapter. It exhausted 24 calls with an empty patch
and 24 failed tool actions. `django-official-results.json` records the official
empty-submission classification, and `django-candidate-audit.json` checks recorded
costs and provenance. This is separate from the invalid infrastructure attempt.

The source issue is from [SWE-bench's public task repository](https://github.com/SWE-bench/swe-bench-tasks)
and [pydata/xarray](https://github.com/pydata/xarray). No reference patches,
evaluation tests, or hidden test names are included in candidate prompts. The model
never successfully read repository source during this run. Source snapshots under
`implementation` are this project's own runner code.

Verify the candidate records from the repository root:

```bash
python3 -m dream_rsi.benchmark_audit \
  examples/benchmarks/evidence/swebench-pilot-xarray-base-retry-20260918
```

`SHA256SUMS` covers the archived run and result artifacts. It is an integrity aid,
not proof of benchmark correctness or an independently signed attestation.

`swebench-pilot-django-20260918` is an interrupted infrastructure attempt, not a
valid model outcome. Python 3.6 could not execute the original trusted file driver.
The interruption note explains why the legacy `budget_exhausted` status is
incorrect, why no prediction exists, and why the final in-flight token count is
unknown. Preserve its cost as overhead; do not silently discard the attempt.

`repository-policy-proposal-20260918` preserves the model's original controller
proposal, complete request/response, training observations, original proposer
source (verified against its recorded hash), and paired-validation plan. The
proposal was generated before looking at validation outcomes. The final comparison
rejected it, and no policy was promoted.

`swebench-policy-django-20260918` records the policy candidate: 24 calls, 14
successful reads, and an empty final patch. `django-policy-official-results.json`
is its official empty-submission report. Its saved-record audit is separate.
`django-only-comparison.json` verifies the registered configuration and reports
the comparison as incomplete at that time because Matplotlib was missing. This prevents
an early acceptance based on an unfinished selected sample. Django source excerpts
in the prompts and tool observations are covered by the included `DJANGO-LICENSE`.

`matplotlib-build-failure.json` records the local compiler failure, full local
build-log digest, and pinned official-image recovery. It is not a model outcome.
`matplotlib-image-version-preflight.json` verifies the imported package version at
the registered base after the Git-metadata compatibility correction. No Matplotlib
model calls preceded this correction.

`swebench-pilot-matplotlib-20260918` records the final fixed baseline attempt:
24 calls, 23 failed tool actions, one successful issue-reproducer command, and an
empty patch. `matplotlib-official-results.json` reports an empty submission and
zero resolutions. The saved-record audit is also included. Matplotlib source and
issue excerpts are attributed under the included `MATPLOTLIB-LICENSE`.

`swebench-policy-matplotlib-20260918` contains the final controller run: 24 calls
and an empty patch. Its audit and official empty-submission report are included.
`repository-policy-final-comparison.json` applies the registered gate to all four
paired runs and rejects the proposal: zero resolutions and no call reduction.
The earlier incomplete report remains preserved as an intermediate record.
