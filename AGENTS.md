This file owns repository-wide working standards. All agents MUST follow them and explicit user instructions; higher-priority platform instructions prevail. CAPITALIZED requirement words have the meanings defined by BCP 14 (RFC 2119 and RFC 8174).

# Document Boundaries

- **AGENTS.md:** working principles and required standards.
- **[Adversarial review skill](.agents/skills/adversarial-review/SKILL.md):** how to run the pre-commit review: reviewer dispatch, integrity snapshots, triage and reporting. Its [scratch-testing recipe](.agents/skills/adversarial-review/references/scratch-testing.md) owns scratch copies, import provenance and mutation evidence.
- **[pyproject.toml](pyproject.toml):** package metadata, the supported Python version, runtime and development dependencies, pytest and coverage options and mypy settings. **[.github/workflows/CI.yaml](.github/workflows/CI.yaml):** CI commands and the tested Python version.
- **[Dockerfile](Dockerfile), [docker-compose.yaml](docker-compose.yaml), [docker-compose.dev.yaml](docker-compose.dev.yaml), [docker_apt_install.sh](docker_apt_install.sh) and [docker_pip_install.sh](docker_pip_install.sh):** the runtime image, system packages, GPU runtime and volume mounts. **[.devcontainer/](.devcontainer/devcontainer.json):** the development container built on them. **[H264 NVENC CQ27.json](<H264 NVENC CQ27.json>):** the HandBrake transcode preset.

Link to the owning document instead of duplicating it. Skills implement these standards; they do not override them. If documents disagree, follow the owning document and confirm any material conflict with the user.

# Scope and Decisions

- If not running in a Docker container, stop and confirm with the user before continuing. This repository assumes its devcontainer with harness permissions set to Full Access or bypass; if the harness enforces restrictions, follow them and report the mismatch.
- Read relevant code and documentation and inspect repository status before editing.
- Give each change a boundary: intent, non-goals, validation and done criteria. Revalidate written tasks against the current code; do not broaden their scope unilaterally, and keep unrelated work untouched.
- State assumptions. Confirm unresolved choices that materially affect scope, user-visible behavior, architecture, correctness or data safety before dependent work. Non-material assumptions MAY be made when repository evidence supports them; name them in the handoff.
- Accepted decisions and user authorization persist; do not ask again about settled choices.
- Subagents MAY be used for independent work; the main agent remains accountable for integration and verification.

# Daemon Contracts

This is a single-module daemon, [`handbrake_daemon/__main__.py`](handbrake_daemon/__main__.py), run as the Docker image's entry point. It scans `MONITOR_DIR` (default `assets/`) for MKV and MP4 files and transcodes those not already encoded in H.264 with HandBrakeCLI on an NVIDIA GPU.

- File selection and skipping, output naming and collision handling, the creation, renaming and deletion of outputs and temporary files, environment variables (`LOG_LEVEL`, `MONITOR_DIR`), exit codes, timeouts, log messages, the HandBrake preset and container configuration (image, packages, mounts, GPU runtime) are user-visible; confirm breaking changes with the user before implementing them.
- Input videos and other pre-existing files under the monitored directory are user data. Changes that could make the daemon modify, overwrite or delete a file it did not create need user confirmation.
- Code MUST run on the Python version in `requires-python`, which CI and the Docker image also use; do not change it without confirming a support change.
- Do not add runtime dependencies without user confirmation. Python dependencies are declared only in `pyproject.toml`; system packages are installed by `docker_apt_install.sh`.
- External tools and filesystem behavior are not portable by assumption: verify assumptions about HandBrakeCLI, MediaInfo, `nvidia-smi`, platforms or filesystems empirically or against version-appropriate documentation. In the devcontainer `assets/` is a network (CIFS) mount, whose timestamp, rename and case-sensitivity semantics can differ from a local filesystem.

# Design and Documentation

- Prefer the simplest cohesive implementation within scope, with clear responsibilities and pure logic where practical. Avoid `Any` and `type: ignore` in new code.
- Before removing a layer, identify the behavior it carries (errors, ordering, messages, user-visible behavior) and keep what is still needed, with its tests.
- New or changed non-test functions, methods and classes MUST have Google-style docstrings covering purpose and any non-obvious contracts, side effects or constraints. Comments explain non-obvious reasons or trade-offs.
- Update documentation the change makes stale, distinguishing verified behavior from proposals and hypotheses. Markdown documentation MUST use one source line per prose paragraph, preserving structural line breaks (headings, lists, tables, code blocks).

# Tests

- Tests MUST protect behavior or an invariant and fail when it breaks. Cover boundaries, failure paths and compatibility contracts; avoid timing-dependent assertions and real sleeps by patching `time`. Test names describe the protected behavior and each test has a one-line docstring.
- Bug fixes SHOULD include a regression test that fails for the original defect and passes with the fix, where reproducible; report any inability to demonstrate the original failure. Assert public results, exceptions and side effects rather than only internal calls.
- Prefer real operations on test-owned temporary files for filesystem contracts, including output collisions, temporary-output handling and failure cleanup where relevant. Use mocks for external tools (HandBrakeCLI, MediaInfo, `nvidia-smi`), time and controlled fault injection, not as the sole evidence that filesystem behavior works.
- New or changed tests MUST import the module under test as `import handbrake_daemon.__main__ as testee`, call it as `testee.function_name`, and patch with `patch.object(testee, 'attribute', ...)`. Order test functions to match the source file.
- Tests MUST NOT run HandBrakeCLI or `nvidia-smi`, use the GPU, reach external services or touch real user files. Both tools are installed in the devcontainer, so an unmocked call really runs. All reads and writes by tests or the code under test stay within test-owned temporary paths, never `assets/` or a real `MONITOR_DIR`. Reading source, installed dependencies and static test fixtures is permitted; this does not permit access to host data or real configuration. Use fixtures that own their teardown, such as `tmp_path` and `monkeypatch`; leave no files, environment variables or working-directory changes behind.
- Tests run in random order under `pytest-randomly`; order-dependent state is a defect, not a flake.
- Changes to data-loss-sensitive behavior (output-path selection and collision handling, temporary-output creation, renaming and cleanup, output deletion after a timeout or duration mismatch, and the file-stability and temporary-file checks that keep incomplete inputs from being transcoded) MUST have targeted mutation evidence produced in a scratch copy under the [scratch-testing recipe](.agents/skills/adversarial-review/references/scratch-testing.md). The reviewer MAY request mutations wherever other protection is doubtful.
- Before removing or weakening coverage, show that a retained test still fails for a mutant breaking the protected property. Consolidating tests that keep the same cases and assertions needs no evidence per removed test body.
- `pyproject.toml` owns pytest and coverage options: measure the `handbrake_daemon` package, show missing lines, and require at least 95% combined statement-and-branch coverage for the project total. This is not a per-file threshold or separate statement/branch minimum. Inspect affected-module coverage; tests lie outside the measured package. A passing total does not excuse untested changed behavior; inspect and explain uncovered lines and branches in affected code. Coverage exclusions and test skips need a narrow rationale and retained verification where feasible; do not lower the gate or exclude application code just to make checks pass.

# Validation and Review

- Before implementation, record a passing baseline of the relevant checks on the starting revision. Fix a failing baseline in a separate, authorized change first.
- The final code, test or configuration candidate MUST pass `pytest`, `mypy handbrake_daemon` and `ruff check .` (matching CI); `mypy .` also checks the untyped tests and is not a gate. The suite is fast: rerun gates after substantive edits instead of reusing earlier results. Resolve new warnings or explain them.
- Container configuration (Dockerfile, compose files, install scripts, devcontainer) cannot be fully exercised from inside the devcontainer. Validate what is feasible, such as `bash -n` for scripts, state what was not run, and ask the user to rebuild or run the container when the change needs it.
- Every non-trivial code, test or configuration change MUST pass the [review procedure](.agents/skills/adversarial-review/SKILL.md#procedure) before commit. A change is non-trivial if it could affect runtime behavior, user-visible behavior, test guarantees, build or container output or filesystem safety; when uncertain, review. Tightly coupled tasks committed together MAY share one review.
- Documentation-only changes (including governance and skill prose) and read-only assessments are exempt from gates and formal review; verify their claims, links and diff instead, preserving safeguards and authorization boundaries. Documentation consumed by build or runtime tools as executable input follows the non-trivial rules.
- Fix validated Blocking findings, then rerun gates and review. Non-blocking findings and Nits MAY be deferred with a recorded reason and revisit trigger, and MUST be reported to the user; deferrals that change scope, behavior or accepted risk need user agreement. Never silently discard or reclassify a finding.
- Never point tests, scratch copies or mutants at real user files or mounted host data, including `assets/` and the Git and SSH configuration mounted by the devcontainer; use test-owned temporary paths instead. Running the daemon or HandBrakeCLI against `assets/` in the devcontainer is permitted. `assets/` is the host's transcode share mounted read-write, and the daemon creates, renames and deletes files there and loops until stopped, so stop it when finished. Other destructive operations on user data require explicit user authorization. Treat credentials and `.env` values as secrets: do not echo, log, commit or transmit them.
- Clean up owned processes and disposable artifacts. Identify owned PIDs before using `kill`; NEVER use `pkill -f`. Before finishing, check the diff, status and any changed guidance against the requested scope.

# Version Control

- Keep functionally independent changes in separate, self-contained commits. Honor requests to leave drafts uncommitted.
- Stage explicit paths and inspect the staged diff and status immediately before committing. NEVER use `git add -A` or `git commit -a`.
- Commit messages MUST start with `<Claude/Codex/...>: <one-line summary>`, followed by a blank line and explanatory paragraphs. Do not add a `Co-Authored-By` line.
