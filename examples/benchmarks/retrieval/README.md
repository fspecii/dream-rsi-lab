# Source-localization experiments

These are development checks on already-exposed pilot tasks, not repair results
or independent validation. The retrieval helper was developed after the fixed
baseline failed. It is not used by the frozen baseline/controller comparison.

`dream_rsi.repository_retrieval` extracts symbols, traceback code lines, and source
filenames from public issue text. It scans bounded tracked source in the base
checkout, ranks matches, and returns line-numbered excerpts with source hashes.
It excludes untracked files, symlinks, and common test/vendor directories from
this initial context. This is an engineering heuristic, not a learned controller.
No reference patches, hidden tests, or solution links are inputs.

| Development case | Source files scanned | Highest-ranked file | Retrieval time |
| --- | ---: | --- | ---: |
| xarray-6461 | 111 | xarray/core/computation.py | 1.93 s |
| Django-11163 | 856 | django/forms/models.py | 1.64 s |

The first result contains the failing expression quoted by the xarray issue; the
second defines the Django function named in its issue. Both scans completed without
reaching their input limits. These checks used the real prepared images, including
Django's Python 3.6 environment. They make no model calls and do not generate patches.
Source retrieval does not prove that a model will understand or correctly repair
the code. The helper is now available as an opt-in development mode:

```bash
python3 -m dream_rsi.benchmark_solver \
  --inputs /path/to/public-inputs.json --instance pydata__xarray-6461 \
  --output runs/xarray-with-context --retrieve-context --steps 24
```

The run saves the exact context before inference, its digest, implementation
snapshot, retrieval time, and total candidate wall time. The candidate audit checks
that every logged request contains that recorded context. Context tampering fails
the audit. The original registered comparison rejects this setting as an unregistered
change. Default inference is unchanged unless the flag is supplied.

`development-plan.json` registers xarray followed by Django, both already-exposed
development cases, before new repair inference. It uses the same model and 24-call
budget with the source context enabled and no learned controller. These results
must remain distinct from the completed pilot and independent final evaluation.

The saved records include the base commit, image ID, retrieval implementation hash,
queries, source excerpts/hashes, scan counts, and timing. Included upstream licenses
cover those source excerpts. `SHA256SUMS` covers the recorded artifacts.
