# Edit recovery development

The preceding source-retrieval replay failed on both exposed cases. Django repeatedly
submitted an exact replacement that did not match exactly once, despite having the
correct file. The revised tool distinguishes missing and ambiguous matches and
returns current excerpts and match locations. After a failed replacement, the loop
requires a successful read or diagnostic command before allowing another edit.
Latest observations appear after initial retrieval so stale source is not the final
context in the prompt. Runtime checks also reject schema-violating repeat edits.

This is a manually engineered workflow, not a learned-controller gain. Passing
fixture tests establishes tool behavior only. The registered 24-call Django replay
uses the same model and seed on an already-exposed development task, with no hidden
evaluator feedback. It exhausted 24 calls with an empty patch: zero resolved. The official evaluator classified the submission as empty and did not run tests. There are no outcome-driven retries or
budget extensions. Independent final evaluation remains necessary.

The completed run made 14 successful reads and 10 failed replacements. Recovery
changed tool behavior but did not repair the task. It used 77,072 input tokens,
1,031 output tokens, and 398.61 seconds of model request time. Full timing is in
the archived result, and the saved-record audit passes. No efficiency gain or
learned improvement is established. The official run ID is
`dream-lab-edit-recovery-django-20260918`.
