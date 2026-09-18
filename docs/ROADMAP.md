# Toward useful developer automation

The lab supports function generation/repair, bounded multi-file project repair,
and the original math task. It is not an established improvement over developer
tools. Repository repair currently uses fixed search and explicit file scopes.

The next evidence should come from real development work:

The selected next acceptance target is a [SWE-bench Verified engineering pilot](SWE-BENCH-PILOT.md).
Its environment positive control passes. The completed fixed pilot resolved 0 of
3 tasks; the proposed controller was rejected after resolving neither validation
task and saving no calls. An issue-derived source retrieval replay also resolved
neither of two exposed development cases. These replays cannot serve as independent
final evaluation. The next repair work must address repeated failed edits and the
lack of effective reproduction and verification, beyond locating source files.

1. **Repository improvement loops.** Snapshots, editable-path constraints, isolated
   project tests, and patch export are implemented. Next integrate these artifacts
   into persistent workspaces and compare learned controllers on independent
   repository tasks. Broaden dependency preparation and language support.
2. **Independent evaluation.** Register a larger, untouched set of generation and
   repair problems with reference tests and explicit failure categories. Compare
   fixed search, simple early stopping, and learned controllers at matched budgets.
3. **Full cost.** Include controller development, validation, sandbox startup, failed
   attempts, tokens, and latency. Measure how many future tasks repay improvement
   overhead; do not report discovery-call savings as net savings.
4. **Reliability.** Expand resume and interruption checks across runtime/model failures,
   add stronger test contracts, and make failure feedback easier to inspect.
5. **Release criteria for stronger claims.** Require reproducible quality preservation
   across multiple models, seeds, task families and independent test sets before
   claiming broad efficiency. Publish unfavorable comparisons alongside improvements.

No benchmark target has been silently declared achieved. The included evidence
records modest successes, failed repairs, and rejected controller proposals.
