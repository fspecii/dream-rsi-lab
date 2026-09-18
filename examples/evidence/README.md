# Local coding experiment evidence — 2026-09-18

These are actual local Ollama runs on the included synthetic function suite. They
are not scripted model fixtures and contain no customer repositories or data.
Model requests/responses, generated source, visible/private evaluator results,
model/image digests, controller proposals and promotion decisions are preserved.
Generated source is an experiment artifact; use the documented Docker runner.

- `code-batches-first`: Qwen 3.5 0.8B, four attempts, proposal version 1.
- `code-batches-gemma`: Gemma 3 4B, four attempts, proposal version 1.
- `code-query-concise`: Gemma 3 4B, two attempts, proposal version 2.
- `code-query-coder`: Qwen 2.5 Coder 7B, two attempts, proposal version 2.
- `gemma-training`: four persistent cycles, 64 calls, no accepted policy change.
- `qwen-coder-training`: three persistent cycles, 33 calls, no accepted policy change.
- `qwen-coder-reserved`: frozen comparison on the four reserved test problems.

Version 2 asks for source only; version 1 also requested a rationale and sometimes
exhausted the response budget. The runs are development observations, not a
controlled head-to-head model comparison. All Qwen Coder training and final test
calls use version 2. Query-value trials used a validation problem, not test data.

The final test split was evaluated once for this release. Both final arms retain
the same fixed policy because no coding policy was promoted. Their comparison
cannot establish learned efficiency. The small suite cannot establish industrial
performance, and future tuning on these results requires a new final test split.

`SHA256SUMS` records every evidence file except itself and this index. Paths inside
workspace state are relative to their archived workspace. Complete discovery worlds
can be replayed without a model; rerunning inference can produce different results.
