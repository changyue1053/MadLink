# Experimental host CI scope

This workflow is prepared on the exact public source tree of
`edf74ca46d620900ddf9365e292e75366a03d87e` (tree
`8436f80ccb7f2b9923f387cee2c5671d75db8abb`). Each future checkpoint-branch
push tests its own commit, not a stale pinned checkout. It never triggers on main.

Only checkout is an external action, pinned to the official v4.2.2 commit.
Repository permission is contents-read; checkout does not persist credentials.
There are no artifacts, cache uploads, releases, publishing steps or secrets.
Raw compiler, test and package logs remain ephemeral on the runner, are not
printed or uploaded. A failure is a failed job, never converted into a pass.
A maintainer may reproduce the named command locally for diagnostics.

Ubuntu 24.04 official apt packages provide host tools. This is a repeatable
recipe, not a bit-reproducible environment: hosted images and security package
versions change. Core tests run with both GCC and Clang; the installed-package
gate requires all four compiler directions. Missing compilers fail that gate.
The existing gate deletes only its disposable producer source/build and moves
its installed prefix before two independent C consumers build, without curl/TLS.
Do not replace it with a build that leaves producer paths accessible.

MadObs headers are fetched from the exact public commit and their two Git blob
hashes verified by the existing script before use. They are neither committed
nor uploaded. This is API-only evidence, not MadObs runtime integration and not
a grant to redistribute upstream materials.

WSS is deliberately not a hosted job in this stage: the official Ubuntu package's
WebSocket-enabled libcurl capability has not been demonstrated here. The local
WSS evidence remains separate; a hosted WSS job requires verifying the actual
linked libcurl capability and then all loopback scenarios, not silently skipping
unsupported cases. No custom curl binary or unpinned source download is added.

Local YAML parsing and command execution do not prove GitHub scheduling or a
hosted Ubuntu pass. Actual remote results must be read after reviewed publication.
