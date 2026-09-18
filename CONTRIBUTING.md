# Contributing

Please start with a small, reproducible problem or proposal. New task support should
include input validation, reproducible evaluation, failure handling, a runnable
example, and tests proving evaluator-only data cannot enter model prompts.

Run `python3 -m unittest discover -s tests -v` before submitting changes. For sandbox
changes, also run `DREAM_TEST_DOCKER=1 python3 -m unittest discover -s tests -v` with
the documented image installed. Keep generated code isolated; do not add a host
execution fallback or broad filesystem/network access to simplify tests.

Keep scientific claims separate from plumbing tests. Scripted model fixtures prove
wiring only. Performance reports must include the frozen model/runtime/policy,
problem splits, seeds, raw evidence, failures, quality, latency, and all call costs.
Never tune on a final test split and continue calling it held out.

Do not commit private suites, credentials, local paths, raw customer data, generated
workspaces, downloaded model weights, or third-party materials without permission.
