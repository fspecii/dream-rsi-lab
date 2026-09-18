# Dream Lab

A local interface for math discovery and Python generation/repair, with persistent
controller improvement. See [developer workflows](examples/code/README.md) for code tasks. This is an independent implementation, not the authors' released code.
Model weights remain fixed: the evolving component is the exploration policy.

## Open

On macOS, double-click **Dream Lab.command** in this folder. Leave its terminal open
while using the app. Or, from this repository, using Python 3.11 or newer:

```bash
python3 -m dream_rsi lab --open
```

Or use `uv run dream-rsi lab --open`. Open http://127.0.0.1:8765 if a browser does not
open automatically. The app and recorded replay need no Python dependencies,
network assets, account, or running model. Live experiments need Ollama running
with a model installed (`qwen3.5:0.8b` is the default).

## First live run

1. Select **New workspace**, name it, and choose an installed model.
2. Leave the math settings at their defaults. Choose three cycles and a maximum
   of 240 new model calls, then **Start improvement**.
3. Watch the stages: collect experiments → edit and replay policies → fresh paired
   checks → keep or promote. Live runs take minutes, depending on the model.
4. Expand completed cycles to compare actual scores and discovery calls. Open
   individual saved trees, inspect policy source, or download the best construction.
5. Use **Pause after current step** to stop cooperatively. Resume with a new call
   allowance. Accepted policy versions can be restored when no cycle is pending.

Cycles and calls are upper bounds. A cycle with no replay improvement finishes
without spending fresh-validation calls. If the allowance cannot cover the next
complete step, the run pauses. The reservation is conservative: an episode reserves
its maximum configured discovery calls, even if the policy ultimately uses fewer.
At most one workspace runs at a time. Starting another run requires the active run
to finish pausing. The server does not schedule future work by itself.

## What qualifies as improvement

The model proposes bounded expressions controlling search priority, eligibility,
parallel batch size, width, and depth. Candidate policies are scored by replaying
saved training trees without generating new solutions. Unsupported replay paths
are rejected or penalized; replay cannot invent evidence.

A replay winner faces the current policy on fresh paired seeds, with identical
frozen training history. Fresh check worlds never enter the policy-editing history.
Promotion requires a valid candidate construction in every pair, no quality loss
in any pair, and either less total discovery work or higher mean solution quality.
A cheap regression is rejected. No replay gain, an incomplete run, or an infrastructure
failure never replaces the current policy. Accepted versions and rejected evidence
remain available.

Fresh checks are small-sample evidence, not proof of a universal improvement.
Policy-editing and validation calls can outweigh future savings. The UI's total
model-call counter includes this overhead; pair tables show discovery calls only.
Best construction can come from training or fresh checks; only training worlds are
fed into subsequent policy edits. This small task often reaches score 1.0 quickly,
so improvements may mostly reduce work rather than raise mathematical quality.

## Persistence and recovery

Everything is stored in `.dream-rsi/` (ignored by Git). Select another location with
`--data-dir /path/to/lab`. Each workspace saves its state, exact constructions,
evaluation diagnostics, policy candidates, paired checks, version history, and raw
model requests/responses. Back up this directory to keep your work.

Completed steps are cached. Pause waits for the current discovery episode or
policy-editing phase to finish. On an abrupt crash, a partially completed step
may be retried under a new attempt ID; all its already logged calls still count.
Completed episodes are reused. A model digest change stops the workspace rather
than mixing different models in its comparisons. Create a new workspace for a new
model. Only one server may own a given data directory.

Use **Discard pending cycle** to abandon its candidate and return to an idle
workspace; evidence and collected training history are retained. This allows you
to restore an earlier accepted policy before starting a new cycle.

The HTTP service binds only to `127.0.0.1`, validates local hosts/origins, and requires
a per-server token for mutations. It is intended for one local user. Stop it with
Ctrl+C in its terminal; restart with the same data directory to reopen workspaces.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

Tests cover replay integrity, expression restrictions, fresh-data separation,
quality-regression rejection, incomplete-check rejection, accepted promotion,
call-budget pause/resume, cooperative pause, restart recovery, rollback, model
failure, process locking, path containment, and HTTP mutation authorization.
The scripted model used in unit tests is clearly separate from real experiment
results. See `docs/experiments.md` for prior measured Qwen experiments.
