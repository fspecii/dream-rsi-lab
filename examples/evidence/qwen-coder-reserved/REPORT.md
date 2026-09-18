# Developer workflow benchmark

Frozen policy vs. fixed search on reserved test problems.
Small starter suite; this does not establish industrial superiority.

| Problem | Fixed private score | Candidate private score | Calls fixed → candidate |
|---|---:|---:|---:|
| flatten-config | 66.67% | 66.67% | 4 → 4 |
| pagination | 75.00% | 75.00% | 4 → 4 |
| run-length | 100.00% | 100.00% | 4 → 4 |
| path-normalize | 100.00% | 100.00% | 4 → 4 |

Fully solved: fixed 2/4, candidate 2/4.
Quality regressions: 0. Call reduction: 0.0%.
Training and validation cost an additional 33 model calls, excluded from the paired call reduction above.

Raw source, prompts, runtime digest, evaluator inputs, token counts, and wall times are saved alongside this report.

No learned policy was accepted. This is a fixed-policy reproducibility check, not evidence of learned improvement.
