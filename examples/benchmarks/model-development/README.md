# Separate model development

The Qwen2.5Coder7B runs repeatedly failed to act on tool observations even when
the correct file, match count, and line positions were supplied. We are preparing
a separate local-model experiment with Qwen3.5 9B using the same repair workflow.
This changes the model, not its weights through training, and is not evidence of
controller self-improvement. Exposed development cases remain exposed.

The [official Ollama package](https://ollama.com/library/qwen3.5:9b) lists a 6.6 GB
Q4_K_M model and Apache 2.0 license. Family-level performance tables on that page
must not be attributed to this 9B package. Its suitability for this project remains
unproven until measured locally. Download and compatibility checks precede any
registered benchmark inference; results are not available yet.

The registered sequence is Django then xarray, 24 calls each, using the unchanged
scoped-edit workflow and retrieval. Explicit request options and package defaults
are recorded separately. This is a comparison of model packages/configurations,
not an isolated model-weights experiment. A neutral schema compatibility check
precedes inference. Neither task is an untouched final evaluation.

The neutral compatibility check passed with one call (48 input tokens, 50 output
tokens, 8.13 seconds including first model load). It returned the requested JSON
read action and line range. Raw request/response and model metadata are preserved
under `compatibility/`. This is transport evidence, not repository-repair evidence.
The registered Django repair run has started; its result is pending.

Django generation finished after 5 calls with a 570-byte patch, two reads, two
replacement attempts (one failed), and a finish action. It used 11,961 input and
385 output tokens, taking 103.01 seconds of model request time. The model ran no
reproducer or tests before finishing, so its completion message is not evidence
of verification. Official evaluation completed and reported **resolved**, with zero infrastructure failures, ambiguous failures, or errors. The public Django issue already
contains a suggested fix; this is not evidence of independent diagnosis.
The registered xarray run has now started without Django evaluator feedback.

`django-official-results.json` is the official summary;
`django-evaluation-method.json` records the exact-image evaluation entry point.
This first successful repair is an exposed development result with a suggested
fix in the public issue, not an independent benchmark score or learned-controller
gain. The xarray outcome remains pending; no two-case aggregate is claimed yet.
