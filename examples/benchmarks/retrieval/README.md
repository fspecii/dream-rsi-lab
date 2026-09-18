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
the code. Integration and repair evaluation remain separate work.

The saved records include the base commit, image ID, retrieval implementation hash,
queries, source excerpts/hashes, scan counts, and timing. Included upstream licenses
cover those source excerpts. `SHA256SUMS` covers the recorded artifacts.
