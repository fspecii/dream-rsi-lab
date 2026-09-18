# Scoped edit development

The preceding recovery experiment produced no patch: the model repeatedly tried
to replace text appearing in two functions. The new general-purpose edit tool
accepts optional inclusive start/end lines, validates the range, and requires
exactly one old-text match inside that range. The model must select the location
and replacement. Malformed, stale, or ambiguous scopes do not modify the file.

The registered Django replay retains the model, seed, retrieval setting, and
24-call budget. This is adaptive development on an exposed case, not independent
evaluation or learned-controller improvement. No retries or budget extensions
are allowed after seeing the outcome. The run completed with an empty patch: zero resolved. The official evaluator classified it as an empty submission and did not execute tests.

The model used all 24 calls: 14 reads and 10 failed replacements. It consumed
72,858 input and 1,252 output tokens, with 409.16 seconds of model request time.
The saved-record audit passes. Full traces and timing are included. The scoped
tool did not yield a successful repair with this model/configuration. No learned
improvement or efficiency gain is established. Official run ID:
`dream-lab-scoped-edit-django-20260918`.
