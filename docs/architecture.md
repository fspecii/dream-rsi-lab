# Implementation and experimental contract

## Modules

| Module | Responsibility |
|---|---|
| `types.py` | Immutable nodes, serializable discovery worlds, stable per-attempt seeds |
| `task.py` | Exact bounded sum–difference evaluation and construction artifacts |
| `model.py` | Ollama transport, raw request/response evidence, usage accounting |
| `expressions.py` | Bounded AST validation and evaluation of controller code |
| `policy.py` | Prefix-derived features, batch selection, pre-episode grid planning |
| `engine.py` | Shared online/replay state machine, real parallel proposal requests |
| `improve.py` | Model-written revisions, replay sweeps, incumbent-preserving selection |
| `experiment.py` | Recursive training, fixed baseline, frozen fresh comparisons |
| `report.py` | Evidence-linked experiment report |
| `tasks/base.py`, `tasks/coding.py` | Task cases, artifact protocol, Python specifications and visible/private tests |
| `sandbox.py` | Disposable Docker execution and host-side answer comparison |
| `code_workflow.py`, `code_benchmark.py` | Function repair/generation, visible selection, reserved test comparisons |
| `lab.py`, `server.py`, `web/` | Persistent workspaces, bounded runs, fresh promotion gates, local interface |
| `cli.py` | Research, replay, lab, code-solve, and benchmark commands |

## Discovery state

A world has a root workspace (initial construction and exact baseline score) and
multiple independent linear branches. Each node has one primary parent. An action
either starts an unopened branch or extends a currently revealed branch frontier.
One action costs one discovery-agent request and one task evaluation. A batch
contains distinct branches, up to the worker cap. All requests in a batch receive
the same observed prefix; outcomes appear only after the batch completes.

Each node stores the full tiny construction artifact, so its workspace is
reconstructible without external dependencies. Math prompts use historical constructions. Code prompts receive the current
problem, visible tests, parent source, and up to six observed attempts from the
same problem. Private evaluations never enter these prompts.

Replay uses a frozen dictionary of recorded nodes. It exposes only legal
structural continuation metadata and already-revealed immutable nodes to the policy.
The policy is never given a world object, hidden results, the replay ceiling, or
the evaluator's normalized attainment. Replays cannot manufacture new outcomes.
Irregular branches exhaust cleanly. Episode caps are charged in calls, not rounds.

Curve accounting charges all attempts in a batch before crediting its best result,
avoiding an arbitrary within-batch ordering advantage.

## Controller features

Branch features include its best successful anchor, latest result, last gain,
stagnation length, failures, last-failure flag, successful attempt count, depth,
remaining structural depth, and whether the action starts a new branch. Global
features include baseline, best revealed score, opened directions, probe count,
decision rounds, worker count and legal action count. There are no branch IDs in
the expression environment; deterministic IDs are only used to break equal ranks.

The complete observed trajectory is scanned to derive these statistics. Failed
attempts do not erase successful anchors. The model can write eligibility rules
that retain a recovery attempt rather than treating every failure as permanent.

Grid planning happens before an episode and uses only completed-history summaries
and hard caps. `beta` is fixed throughout an episode. Candidate beta sweeps are
offline diagnostics; `beta` does not adapt from hidden online information.

The original hard caps and the realized grid are stored separately. Replay must
plan against the original caps, not shrink an already reduced grid a second time.
A requested plan outside the frozen world's support rejects the candidate. For
manual CLI replay, `--history` supplies earlier world files for planning; omitting
it uses a cold-start planning context.

More precisely, the deployment/default beta must be supported on every world to
be selectable. Other beta-sweep points can be out of support after the policy has
collected a smaller grid. Those points are labeled explicitly with no paper score;
in the optional AUC surrogate, unsupported worlds receive zero attainment and a
maximal serial penalty rather than being silently omitted from the average.

## Policy selection

Every phase starts by reevaluating the incumbent on the current frozen pool.
Each newly proposed expression program is validated, evaluated separately on every
world and beta, and archived. Invalid syntax or numerical errors reject a proposal
without pretending it received a valid score. Model infrastructure failures abort
the run and preserve evidence instead of becoming artificial scientific failures.

Selection is deterministic with stable incumbent tie-breaking. The replay score
of the selected policy cannot decrease on that same pool. This guarantee says
nothing about out-of-sample improvement or about comparison across changing pools.

The paper objective and appendix-style AUC objective are separate CLI modes.
Their numbers must not be mixed. In AUC mode, a world's realized best score is used
only by the evaluator to normalize attainment; it never enters runtime features.

## Paper fidelity

| Paper mechanism | Implementation | Scope / difference |
|---|---|---|
| Fixed coding model and evaluator | Fixed Ollama model digest and exact evaluator | Integer constructions or standard-library Python functions; no unrestricted repository editing |
| Executable exploration policy evolves | Model-authored ranking, eligibility, batching and planning expressions | Bounded expression language rather than arbitrary controller Python |
| Saved workspace per attempt | Executable construction, parent linkage, measured result, model record | Tiny self-contained artifacts rather than general filesystem snapshots |
| Online exploration then replay pool | Completed live worlds accumulate each cycle | Small sum–difference and Python function tasks |
| Prefix-only replay | Shared state machine, fresh prefix for every evaluation | Uses Appendix B's arbitrary legal roots; Section 3's formal root reveals earliest child |
| Cheap offline evaluation | No discovery-model or task-evaluator calls in replay | Policy-development inference still costs time/tokens and is reported |
| Quality, work, parallelism | Section 3 objective plus separate appendix-style option | Coefficients and AUC discretization are explicit demo choices |
| Best policy redeployed | Selected controller runs the next live cycle | No guarantee that fresh outcomes improve |
| Recursive fixed-exploration control | Same bootstrap, model, evaluator, caps, own recursive history | Fresh comparison additionally shares identical training context to isolate policy |
| Empirical performance | Fresh paired episodes and full raw logs | Not a reproduction of eight published benchmarks or state-of-the-art scores |

Historical replay assumes stored outcomes remain useful when a new policy changes
execution order and visible cross-branch context. The real discovery agent can
respond differently under that changed context. Fresh evaluation is required
precisely because this approximation is not a learned generative world model.

## Tests

The test suite includes exact known sum–difference counts; malformed constructions;
artifact round-tripping; hidden-score perturbation; deterministic replay resets;
live/replay transition equivalence; strict call budgets; simultaneous batch
visibility; irregular support; empty stopping; recovery anchors; illegal batches;
expression access restrictions; executable-source equivalence; incumbent retention;
invalid candidate rejection; and offline model-call accounting.

Scripted agents appear only in tests. Their scores are never presented as evidence
of language-model discovery or as benchmark results.

The end-to-end test also exercises continuation from training-only state, fresh
seed separation, model-call import accounting, report generation, and rejection
of a deliberately tampered headline result by the independent audit command.

## Developer workflow contract

`TaskCase` separates public problem input and baseline artifacts from private
assessment data. `CodingTask` implements the artifact protocol; the original math
path remains compatible with older saved worlds. Code worlds store the task name,
problem identifier, source artifacts, suite digest, and proposer prompt version.

Visible tests guide search and select one artifact. Ties retain the baseline or
earliest winner. Only then do private tests assess that selected artifact; they
cannot choose a different answer. Docker receives source and inputs, while expected
answers remain in the host process. The runner fails closed without Docker and
pins the interpreter image ID. See the security document for isolation limits.

Persistent code workspaces collect training problems and compare replay-selected
policies on distinct validation problems. Promotion requires no private-score loss
in any pair, positive candidate quality in every pair, and better mean quality or
fewer discovery calls. Private aggregate validation feedback can influence later
controller edits, so repeated validation is adaptive, not an untouched final test.

`code-benchmark` freezes the workspace policy, model digest, runtime image, suite,
and training history, then compares against fixed search on the reserved test split.
It alternates arm order and records per-problem quality, model calls, tokens and
wall time, with training overhead separately reported. A v00 workspace is explicitly
a fixed-policy reproducibility check. Benchmark results never update the workspace.

Docker tests cover real execution, UID, network restrictions, a read-only root,
exception handling, output overflow, timeouts, and cleanup. Fixture tests additionally
check split separation, prompt privacy, frozen benchmarking, and durable code loops.
These implementation tests do not establish model performance.
