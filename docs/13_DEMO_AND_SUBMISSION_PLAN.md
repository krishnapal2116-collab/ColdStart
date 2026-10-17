# ColdStart Demo and Submission Plan

**Status:** Committed demo fixtures and commands are implemented; final recording remains pending
**Version:** 0.3
**Target duration:** Two to three minutes

## 1. Audience takeaway

ColdStart finds “works on my machine” risks safely, explains the evidence, and does not claim a repository is reproducible merely because static files look plausible.

## 2. Opening problem statement (20 seconds)

“A project can work for its author and fail for a reviewer because the runtime, dependencies, configuration, or test command was never made reproducible. ColdStart audits that evidence without running untrusted repository code.”

## 3. Demonstration repository

The committed fixture is the deliberately defective Python repository at `examples/defective-python/`. It contains:

- a Python package metadata file;
- a README with an incomplete setup path;
- a missing lockfile for a declared dependency;
- a runtime declaration conflict;
- incomplete test/configuration evidence;
- a developer-specific path indicator;
- no real credentials.

A separate committed `examples/clean-python/` fixture contains corrected, bounded P0 evidence. `tests/test_phase6_m6_examples.py` audits both fixtures through the real CLI and verifies that static inspection does not modify them.

## 4. Demo command and sequence

Defective-fixture command:

```text
PYTHONPATH=src python -m coldstart audit examples/defective-python --format terminal
```

Sequence:

1. Show the repository path and read-only boundary.
2. Run the actual command.
3. Point to one or two stable check IDs and relative evidence paths.
4. Explain the distinction between `failed`, `not_applicable`, and `not_verified`.
5. Show the remediation guidance.
6. Correct the fixture in a separate committed change or prepared branch.
7. Run the actual command against `examples/clean-python`.
8. Show that the findings changed, while any unexecuted test/Docker verification remains `not_verified`.

P1 optional segment, using the implemented plan/authorization flow:

```text
coldstart verify examples/clean-python --kind tests --offline --plan
coldstart verify examples/clean-python --kind tests --offline --authorize
```

Show the proposed Docker-isolated plan and explicit approval. The current runner reports an authorized offline test as `not_verified` if Docker or the pinned image is unavailable, without falling back to host execution. If Docker is unavailable or execution is not included in the release, state that honestly instead of simulating a pass.

## 5. Correction story

The correction should add only the evidence needed by the finding: align the runtime declaration, add the appropriate lock/pinned policy, document setup/test/configuration, and remove the machine-specific path. The demo must not edit the repository automatically because auto-fix is P2.

## 6. README checklist

- [ ] One-sentence product definition.
- [ ] Safe default and limitations visible near the top.
- [ ] Exact installation and runtime instructions.
- [ ] `coldstart audit` examples.
- [ ] Terminal/JSON output examples without secrets.
- [ ] `make test` command.
- [ ] Docker build/run command and Docker limitation note.
- [ ] P0/P1/P2 scope.
- [ ] Actual verification results with dates/commits.
- [ ] Troubleshooting and contribution guidance.

## 7. GitHub/repository checklist

- [ ] Repository name and description match ColdStart.
- [ ] License and contribution guidance are present if approved by the owner.
- [ ] No secrets, local paths, virtual environments, build outputs, or generated reports are committed unintentionally.
- [ ] Pinned runtime and lockfiles are tracked.
- [ ] Dockerfile and `make test` work from a clean checkout.
- [x] Defective and clean fixtures are included and documented.
- [ ] Issue/PR templates do not promise unsupported features.

## 8. Docker and offline checklist

- [ ] `docker build --pull=false --tag coldstart:demo .` actually ran.
- [ ] Docker smoke command actually ran.
- [ ] `make test` actually ran with network disabled.
- [ ] Static audit actually ran without project execution.
- [ ] Any P1 verification has an execution receipt.
- [ ] Docker unavailable behavior was tested or clearly marked as an environment gap.

## 9. Recording checklist

- [ ] Show commands and real terminal output, not prewritten claims.
- [ ] Do not expose usernames, tokens, private paths, or unredacted source.
- [ ] Keep the demo within three minutes.
- [ ] Explain at least one limitation.
- [ ] Keep the final report and commit IDs available for review.

## 10. Submission checklist

- [ ] Owner-approved document pack and implementation.
- [ ] P0 acceptance checklist complete.
- [ ] No release-blocking security or reproducibility defect.
- [ ] All claims backed by recorded commands.
- [ ] Demo path reproducible from repository instructions.
- [ ] Competition submission contains no simulated verification result.
