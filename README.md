# Dream RSI Lab

An independent, local implementation of exploration-policy improvement inspired
by [Dream-RSI](https://github.com/zhengkid/Dream-RSI).

Dream Lab generates and repairs Python functions against executable tests, then
uses saved experiments to propose changes to its search controller. It also includes
a small mathematical discovery task. Model weights stay fixed.

This is **not Google's code release**, an official reproduction, or an affiliated
project. It is an experimental implementation with explicit limitations. The
included coding suite is small; it does not establish industry-wide superiority.

## What works

- Local browser workspaces with bounded runs, pause/resume, durable evidence,
  source inspection, downloads, policy version history, and rollback.
- Multi-file Python project repair from explicit snapshots and editable paths,
  with real unittest/pytest commands and reviewable patch export.
- Python generation/repair from problem descriptions and optional starter code.
  Bring your own JSON suite with visible and private tests.
- Function/snapshot Docker execution with no network or host-directory mounts, a non-root
  user, read-only root, and time/memory/process/output limits.
- Replay-based controller edits. Candidates must pass fresh paired comparisons
  before promotion; cheaper quality regressions are rejected.
- Private tests assess the program chosen by visible tests. Separate train,
  validation, and test problem splits support final controller comparisons.
- Exact math evaluation and an offline recorded replay needing no model.

## Measured status

The initial reserved coding check fully solved **2 of 4 problems**. No coding
controller was promoted, and the final comparison showed **0% call reduction**.
A separate batching repair passed all private checks. These are small local results;
[successful and failed traces](examples/evidence/README.md) and
[the full measurements](docs/experiments.md) are included.

## Quick start

Use macOS or Linux, Python 3.11+, Ollama, and Docker:

```bash
git clone https://github.com/fspecii/dream-rsi-lab.git
cd dream-rsi-lab
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
ollama pull gemma3:4b
docker pull python:3.12-slim
python3 -m dream_rsi lab --open
```

Start Ollama and your Docker daemon first. On macOS, Colima is supported; start an
installed instance with `colima start`. Open `http://127.0.0.1:8765`, select **New
workspace**, and choose **Developer · Python generation and repair**. A small
starter suite is included. The application does not download models automatically.

The offline **Recorded replay** works without Docker or Ollama. Math experiments
can use `qwen3.5:0.8b`. [Full lab guide](LAB.md) ·
[Developer workflows and suite format](examples/code/README.md).

## Repair one function

```bash
python3 -m dream_rsi code-solve \
  --suite examples/code/workflows.json --problem batch-items \
  --model gemma3:4b --branches 2 --depth 2 \
  --output runs/my-repair
```

Inspect `solution.py`, `result.json`, raw model calls, and candidate test results in
the output directory. Only visible tests select the returned program; private
checks report whether it generalizes to additional cases.

## Repair a project

```bash
ollama pull qwen2.5-coder:7b
python3 -m dream_rsi repo-solve \
  --repo examples/repository --task examples/repository/task.json \
  --branches 1 --depth 3 --output runs/project-repair
```

This exports a patch after running project tests in Docker. It leaves the source
checkout unchanged. [Project configuration, dependencies, and limits](examples/repository/README.md).
Repository repair currently uses fixed search; persistent learned repository
controllers remain future work.

An experimental [SWE-bench candidate runner](docs/SWE-BENCH-PILOT.md) also supports
prepared repository images, issue-driven code inspection, edits, and visible tests.
Its container profile differs from snapshot repair; see [security scope](SECURITY.md).
Its baseline uses a fixed tool loop. Two of three pilot tasks each produced an
empty patch after 24 calls; Matplotlib remains pending. No broad benchmark
performance or repository-controller improvement is established.

## Improvement and evidence

The model proposes search-controller expressions for exploration width, depth,
priority, batch size, and stopping. Historical replay measures these changes without
new discovery calls. Promising policies face the incumbent on paired validation
problems. Only a candidate preserving quality in every pair and improving quality
or reducing calls can replace it.

Use `code-benchmark` to evaluate a frozen code workspace on its reserved test split.
Reports include private-test scores, completely solved problems, regressions,
calls, tokens, latency, and separate training overhead. See the
[experiment notes](docs/experiments.md) for measured local results and their limits.

Self-improvement is not guaranteed. A run may reject every proposed edit. Savings
in later discovery calls do not automatically repay the cost of training and
validation. A smaller test score is never hidden behind a cheaper-call headline.

## Scope and limitations

- Function tasks use JSON inputs and outputs. Project tasks support explicitly
  selected UTF-8 files and standard unittest/pytest reports. Dependencies must be
  prepared in a Docker image; unrestricted repository access is not supported.
- A local container is not a multi-tenant hostile-code service. Do not expose the
  local server publicly. No generated code runs on the host as a fallback.
- Tests are part of your specification. Incomplete tests can reward incorrect code.
  Repeated validation can overfit; keep final test problems untouched.
- The starter suite is a functional smoke test, not a representative industrial
  benchmark. Small local models can fail even basic repairs.
- This implements selected ideas from the paper; it does not reproduce its full
  task coverage, model scale, distributed infrastructure, or reported results.

## Development

```bash
python3 -m unittest discover -s tests -v
DREAM_TEST_DOCKER=1 python3 -m unittest discover -s tests -v
```

The second command includes real isolation, timeout, overflow, and cleanup checks.
No model inference is required for the test suite. See [CONTRIBUTING.md](CONTRIBUTING.md),
[architecture](docs/architecture.md), [next milestones](docs/ROADMAP.md), and [SECURITY.md](SECURITY.md).

MIT license for this independent implementation. Original research is credited in
[THIRD_PARTY.md](THIRD_PARTY.md); the upstream paper and branded assets are not
redistributed here.
