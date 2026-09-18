# Repair a project and export a tested patch

`repo-solve` works on multiple files in a local project. You specify which files
enter the snapshot, which files the model may change, and how to run the project's
tests. Each attempt executes in a fresh Docker container. Source files in the
original checkout remain unchanged; the result is a patch for review.

The included fulfilment example has interacting shipping and checkout bugs and
seven unittest methods. From the repository root, with Ollama and Docker running:

```bash
ollama pull qwen2.5-coder:7b
docker pull python:3.12-slim
python3 -m dream_rsi repo-solve \
  --repo examples/repository --task examples/repository/task.json \
  --model qwen2.5-coder:7b --branches 1 --depth 3 \
  --output runs/fulfilment-repair
```

Exit status is **0** when the selected patch passes the configured test gate,
**2** when tests still fail, and **1** for an input or infrastructure error.
A failed run can still export the best partial repair, clearly marked in
`result.json`. Inspect `patch.diff`, `selected-files.json`, and the test output
before applying anything. Existing run directories are never overwritten.

To check a patch against the project root before applying it:

```bash
cd examples/repository
git apply --check ../../runs/fulfilment-repair/patch.diff
```

The command above only checks applicability. Applying the patch is a separate
manual `git apply` step after review. If your checkout changed since the snapshot,
review those changes and rerun the repair as needed.

## Describe your project task

Use the example `task.json` as a starting point:

- `include`: project-relative file names or glob patterns to snapshot. Include the
  implementation, tests, and required configuration. Avoid broad patterns that
  could include secrets. Git metadata and credential-directory paths are rejected.
- `editable`: exact paths the model may replace, including explicitly allowed new
  files. Existing editable files must be included in the snapshot.
- `test_files`: exact included test-file paths. These cannot be editable.
- `context`: optional exact included files the model may read, beyond editable
  source. Tests are not automatically included in model prompts; failing-test
  output is visible feedback and may reveal assertions.
- `command`: an argument array executed inside the container, never a host shell.
- `test_framework`: `unittest` (default) or `pytest`, using standard summary output.
- `minimum_tests`: a positive lower bound on executed tests. Set it to the expected
  suite size so accidentally running fewer tests cannot look successful.

A pass requires a successful command, sufficient executed tests, a full test
quality score, no output overflow, and unchanged protected snapshot files. Partial
scores reflect passed test methods; repeated failing unittest subtests count their
parent once. Unknown failure summaries score zero. Custom test runners, unusual
report formats, expected failures, and plugins may need an explicit adapter.

These are **visible project tests**, not independent hidden validation. A model
that games test output or manipulates the test runtime could defeat this quality
gate. Protected-file checks catch ordinary mutations, not every possible deceptive
program. Keep independent acceptance checks for consequential changes.

## Dependencies and boundaries

The default image supports Python standard-library projects. For pytest or other
dependencies, prepare an image yourself and pass `--image your-image:tag`. The image
must provide `python`; pin dependencies in that image before the run. A typical
trusted dependency-build stage uses a pinned, hashed requirements file:

```dockerfile
FROM python:3.12-slim
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
```

The repair run pins the installed image ID, disables network access, and does not
install dependencies or mount your checkout, Docker socket, or host credentials.
It runs as an unprivileged user with the same resource limits as function tasks.
`--timeout` sets the per-attempt wall limit (1–120 seconds, default 60).

Snapshots currently support at most 200 UTF-8 files, 128 KiB per file, and 1 MB in
total. Model context is capped at 64 KiB. Symlinks and special files are rejected;
hidden directories, build outputs, and dependency trees are not traversed. The
runner stages text files; use interpreter commands rather than relying on original
executable bits. Large/binary assets and general language-toolchain support need
further work.

This command uses bounded fixed search and exports a patch. Persistent repository
workspaces and learned repository-controller comparisons are not yet integrated
into the browser lab. The function-level and math workflows retain those features.

## Evidence

A run saves the exact project snapshot, baseline result, every proposal and test
result, model requests/responses, selected patch, model and image digests, usage,
and implementation source snapshots with SHA-256 hashes. These are local files;
do not publish them if your project contains private code or data.

To recheck an exported patch without inference, run
`python3 -m dream_rsi repo-verify runs/fulfilment-repair`. The verifier checks the
snapshot digest, implementation hashes where recorded, selected-source provenance,
diff contents, and selected test result.

The [development evidence](evidence/README.md) includes one 7/7 repair and two
incomplete 5/7 repairs. These trials do not establish reliable repository repair
or a benchmark improvement.
