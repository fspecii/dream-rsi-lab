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
evaluator feedback. Its outcome is pending. There are no outcome-driven retries or
budget extensions. Independent final evaluation remains necessary.
