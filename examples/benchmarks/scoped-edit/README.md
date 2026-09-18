# Scoped edit development

The preceding recovery experiment produced no patch: the model repeatedly tried
to replace text appearing in two functions. The new general-purpose edit tool
accepts optional inclusive start/end lines, validates the range, and requires
exactly one old-text match inside that range. The model must select the location
and replacement. Malformed, stale, or ambiguous scopes do not modify the file.

The registered Django replay retains the model, seed, retrieval setting, and
24-call budget. This is adaptive development on an exposed case, not independent
evaluation or learned-controller improvement. No retries or budget extensions
are allowed after seeing the outcome. Results are pending.
