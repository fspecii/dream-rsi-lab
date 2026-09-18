# Repository repair development evidence

All three runs used local Qwen 2.5 Coder 7B on the same synthetic fulfilment task.
These are development trials, not an independent benchmark or a controlled
comparison of search policies. Test output was visible during repair.

| Run | Scoring contract | Model calls | Selected patch |
|---|---|---:|---|
| repository-fulfilment-qwen | Initial binary test gate | 3 | 7/7 tests pass |
| repository-fulfilment-scored | Version 2 partial-credit gate | 3 | 5/7 tests pass |
| repository-fulfilment-default | Version 2, two search directions | 6 | 5/7 tests pass |

The initial run predates implementation-source snapshots; its recorded partial
scores are binary. Both version 2 runs preserve implementation snapshots and hashes.
All three runs used a 1,600-token proposal limit; the shipped repository adapter
allows 8,192 tokens for larger file responses. No recorded response was truncated.
Do not turn the single successful trial into a reliability claim. The later
incomplete patches are retained and the CLI exits with status 2 for them.

Each selected patch was independently reexecuted in the pinned Docker image, with
its exported diff and model-source provenance checked. From the repository root:

```bash
python3 -m dream_rsi repo-verify examples/repository/evidence/repository-fulfilment-qwen
python3 -m dream_rsi repo-verify examples/repository/evidence/repository-fulfilment-scored
python3 -m dream_rsi repo-verify examples/repository/evidence/repository-fulfilment-default
```

The first command succeeds; the other two verify the incomplete result and exit 2.
Verification evaluates the selected patch, not every historical proposal or a
stronger independent acceptance suite. The checksum file covers the evidence
files except itself and this index. No customer code or data is included.
