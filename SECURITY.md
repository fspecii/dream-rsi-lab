# Security scope

Dream Lab is a local, single-user experimental application. Its HTTP service binds
to loopback, validates Host and Origin, and requires a session token for mutations.
It is not designed for public hosting or untrusted multi-tenant use.

Generated Python runs only in a constrained Docker container. Expected test answers
remain in the host evaluator. Containers have no network or host project mounts,
run as an unprivileged user with dropped capabilities, and are resource-limited.
Container escape vulnerabilities and host/runtime compromise remain outside this
application's protection. Keep the host and runtime updated.

Custom suites and model responses are untrusted data. Private tests are private from
the proposing model, not encrypted from the local computer owner. Workspaces store
raw prompts, responses, source, and evaluator inputs. Treat local workspaces as
sensitive if your own tasks contain sensitive information.

For a vulnerability, contact the repository maintainer privately through GitHub
before posting exploit details. Do not include secrets or private customer data in
an issue or reproduction. The repository currently makes no support or disclosure
response-time guarantees.

Repository repair copies only configured text files into the container and exports
a patch; it does not mount or edit the host checkout. Non-editable file hashes are
checked after tests. Project-test summaries are a quality signal, not an
adversarially secure oracle: generated code can influence its test process. Use
independent review and acceptance checks for consequential changes.
