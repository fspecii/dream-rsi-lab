# Python generation and repair

Developer tasks are executable Python functions with JSON inputs/outputs. A suite
contains a specification, optional buggy starter code, visible tests, and private
final checks for each problem. The included suite covers text normalization,
batching, bookings, CSV aggregation, event deduplication, inventory deltas, URL
queries, retries, configuration flattening, pagination, and path processing.

This is a function-level coding workflow, not yet a general repository-editing
agent. It supports the Python standard library; project dependencies and arbitrary
unit-test commands are future work. The starter suite is a small functional check,
not evidence of industrial superiority.

## Requirements

- Python 3.11+, Ollama, and an installed model.
- A running Docker-compatible daemon. For an installed Colima instance on macOS: `colima start`.
- Pull the official interpreter once: `docker pull python:3.12-slim`.

The sandbox pins the local image digest for reproducible execution. It never
silently executes generated source on the host when Docker is unavailable.

## Browser

Run `python3 -m dream_rsi lab --open`. In **New workspace**, choose
**Developer · Python generation and repair**. The interface selects Gemma 3 4B if
it is installed, based on the initial local repair check. You can choose another
model explicitly. Code workspaces use a smaller initial search than math ones.

Optionally upload your own suite JSON. The exact suite is snapshotted with the
workspace and its digest is checked when resuming. Include at least one train
problem and as many distinct validation problems as your selected fresh-pair count.
Problems in the test split are reserved for final evaluation, not policy training.

Candidate programs receive visible-test feedback during search. After selecting a
program solely by visible score, private tests assess it. Controller promotion uses
private-test results across distinct validation problems paired with the incumbent.
No private test inputs or answers are placed in prompts. Reusing a validation set
across cycles can still overfit policy selection; a separate untouched test split
is needed for final performance claims.

## One problem from the CLI

```bash
python3 -m dream_rsi code-tasks examples/code/workflows.json
python3 -m dream_rsi code-solve \
  --suite examples/code/workflows.json --problem batch-items \
  --model gemma3:4b --branches 2 --depth 2 \
  --output runs/my-code-repair
```

The output contains `solution.py`, raw model calls, the exact suite and manifest,
all candidate source and visible evaluations, and `result.json` with the selected
solution's private assessment. Existing output directories are never overwritten.
The selected source may be the starter if no candidate improves visible quality.
The private assessment never breaks ties or retroactively selects another answer.

## Suite format

```json
{
  "version": 1,
  "name": "My developer tasks",
  "problems": [{
    "id": "addition",
    "split": "train",
    "description": "Return the sum of two integer arguments.",
    "entrypoint": "add",
    "starter": "def add(a, b):\n    return a - b\n",
    "visible_tests": [{"args": [2, 3], "expected": 5}],
    "hidden_tests": [{"args": [-4, 3], "expected": -1}]
  }]
}
```

Tests accept `args`, optional `kwargs`, and `expected`. Results use JSON structural
equality; booleans are not accepted as integers. Omit `starter` for generation from
scratch. There may be 1–128 visible and private tests per problem. Source is capped
at 32 KiB, suites at 2 MB, and sandbox transport input at 256 KiB.

## Isolation and limits

Each candidate runs as a non-root user in a fresh container, with no network,
no host project/credential mounts, a read-only root, dropped capabilities,
256 MiB RAM, one CPU, 32 processes, limited output, and a wall-time limit.
Expected answers remain outside the container; the host compares returned values.
The container is removed after success, failure, output overflow, or timeout.
This is a local experimental runner, not a multi-tenant hostile-code service.

```bash
DREAM_TEST_DOCKER=1 python3 -m unittest discover -s tests -v
```

The Docker checks execute passing/failing programs, exceptions, an infinite loop,
excessive output, and verify non-root identity, network isolation, read-only root,
and cleanup. Normal unit tests skip Docker checks unless explicitly enabled.

## Evaluate the frozen controller

After a code workspace is idle with no pending cycle, use its 12-character directory
name under `.dream-rsi/sessions/`:

```bash
python3 -m dream_rsi code-benchmark \
  --workspace YOUR_WORKSPACE_ID --repeats 1 \
  --output runs/my-reserved-code-benchmark
```

This compares the accepted controller with fixed search on every problem in the
reserved `test` split. Each arm receives the same problem, seed, visible tests,
training history, and maximum budget. Selection uses visible tests only; private
checks run on the selected program. The report includes fully solved problems,
private scores, regressions, calls, tokens, timing, and separate training overhead.
The benchmark snapshots its policy and never changes the workspace.

Repeatedly looking at the test report and tuning against it turns that split into
validation data. For a credible final claim, register a new untouched test suite and
run a larger evaluation. A workspace still on v00 compares fixed search to itself;
it does not constitute evidence of learned improvement.
