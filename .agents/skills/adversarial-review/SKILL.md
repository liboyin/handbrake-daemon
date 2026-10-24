---
name: adversarial-review
description: Independently review non-trivial code, test, or configuration changes and return reviewer-owned findings without editing the repository. Use when AGENTS.md requires pre-commit review.
---

# Adversarial Review

[AGENTS.md](../../../AGENTS.md#validation-and-review) owns when review is required and its exemptions. This skill owns how: dispatch, integrity snapshots, investigation and reporting. The [scratch-testing recipe](references/scratch-testing.md) owns test and mutant execution; read it before running either. The reviewer investigates and classifies findings without editing the repository; the main agent owns implementation and dispositions.

## Reviewer

Use one independent Codex reviewer per change (or tightly coupled group), started without the main agent's conversation, so that review comes from a different model family than most implementation work. Claude Code agents MUST NOT substitute a Claude subagent. Continue the same session for follow-ups; replace it only for unrelated work, a substantial redesign or an unavailable session, recording the reason and transferring outstanding findings. Use model `gpt-6.1-sol` with high reasoning effort unless the user selects otherwise.

- **Codex:** `spawn_agent` with `fork_turns: "none"`, `model: "gpt-6.1-sol"` and `reasoning_effort: "high"`; continue with `followup_task`.
- **Claude Code:** check `command -v codex` and `codex login status`, then run `codex exec --dangerously-bypass-approvals-and-sandbox --model gpt-6.1-sol -c model_reasoning_effort="high" --json <prompt> < /dev/null` and record the returned session ID. Continue with `codex exec resume --dangerously-bypass-approvals-and-sandbox --model gpt-6.1-sol -c model_reasoning_effort="high" <SESSION_ID> <prompt> < /dev/null`. Keep stdin closed as shown, or codex waits for more prompt input; use the recorded ID, not `--last`. The bypass flag lets the reviewer run scratch tests; AGENTS' devcontainer assumption and the read-only rule below still apply.

If the reviewer, model or authentication is unavailable, report the blocker and ask the user; do not install tools, substitute another reviewer or claim a verdict. Wait for each invocation to finish and check its exit status before acting on the report.

## Procedure

### 1. Freeze, gate and snapshot — main agent

Freeze the candidate and make `pytest`, `mypy handbrake_daemon` and `ruff check .` pass on it. Create a working record in an owned directory outside the repository (`RECORD_DIR`, for example in the session scratchpad), disclosing it if storage is temporary. It holds:

- **Boundary and target:** intent, acceptance criteria, starting revision, in-scope uncommitted and untracked paths, and unrelated dirty paths to ignore.
- **Candidate copy:** for uncommitted candidates, `git diff --binary HEAD` plus copies of in-scope untracked files (a diff omits their contents), so follow-ups can review the delta.
- **Reviewer, checks and findings:** session ID, model and effort; gate commands and results; the reviewer's report, then the main agent's validations and dispositions.
- **Integrity, mutation evidence and cleanup**, as produced below and by the [scratch-testing recipe](references/scratch-testing.md#mutation-evidence).

Then snapshot the repository from its root so reviewer side effects can be detected, passing in-scope untracked regular files as arguments (`sha256sum` follows symlinks):

```bash
snap() (
  set -euo pipefail
  git rev-parse HEAD
  git --no-optional-locks status --porcelain=v1 --untracked-files=all
  git diff-index --cached -p --binary HEAD | sha256sum
  git diff-files -p --binary | sha256sum   # porcelain `git diff` rewrites the index
  if [ $# -gt 0 ]; then stat -c '%a %F %N' -- "$@"; sha256sum -- "$@"; fi
)
snap <in-scope untracked files> > "$RECORD_DIR/before.txt"
```

A non-zero exit means the snapshot is unusable; resolve the cause before review. The output covers HEAD, staged and unstaged content (including mode and symlink changes), the untracked path list and the selected untracked files' modes and contents. It never reads ignored files or the contents of `assets/`, which is ignored. It detects accidents; it is not a security boundary.

### 2. Dispatch — main agent

Ask the reviewer to read this skill and perform step 3. Supply only: repository path and exact target (dirty tree, commit or range; the prior target and delta for follow-ups), in-scope paths and untracked files, unrelated dirty paths to ignore, a few sentences of purpose, and the working-record location. Add accepted decisions or constraints only when needed. Do not inline the diff, conversation, suspected defects or main-agent conclusions. Answer reviewer questions with minimal facts and note them in the record.

The repository stays read-only for the reviewer. Writing evidence outside it is fine; tests, mutants and other writable commands run only in a scratch copy under the [scratch-testing recipe](references/scratch-testing.md). The reviewer never runs the daemon, HandBrakeCLI or `nvidia-smi` against `assets/` or other host data.

### 3. Investigate and report — reviewer

Read current AGENTS.md, the complete candidate and the relevant source, tests and documentation. Try to falsify the change with boundary and failure cases, and look for tests that pass for the wrong reason, such as mocks of `Path` methods or external tools that hide the real behavior. Where relevant, scrutinize case-insensitive suffix and temporary-file matching, output naming and collisions, the file-stability check on files still being written, MediaInfo parse failures and missing tracks, HandBrakeCLI exit codes and timeouts, temporary-output rename and cleanup, output deletion after a duration mismatch, whether one failing file can stop the daemon, GPU health and restart behavior, environment-variable handling, and container, mount and dependency configuration. Distinguish atomic operations from check-then-act races with other writers in the monitored directory, and local-filesystem behavior from network-share behavior. Do not manufacture findings or treat taste as a defect.

Classify each evidenced finding:

- **Blocking:** must be resolved before commit.
- **Non-blocking:** a genuine issue that may reasonably be deferred.
- **Nit:** low-impact style or readability issue with an obvious local remedy.

Rely on the supplied passing gates; run focused tests only for a specific concern. Check required mutation evidence (AGENTS' [Tests](../../../AGENTS.md#tests)) against the candidate, filling gaps in scratch or returning `Review blocked`, and request more when protection is doubtful. Return the [report](#report), save essential evidence outside scratch, and clean up owned scratch and processes. Propose remedies if useful, but never edit the repository.

### 4. Validate and disposition — main agent

Rerun `snap` with the same arguments and `diff` it against `before.txt`; an unexplained change blocks acceptance of the review. Then independently investigate each finding without changing its classification:

- **Blocking:** validate the claim before fixing. If it does not hold, send counterevidence to the reviewer; if an equivalent Blocking finding stays unresolved across two rounds, ask the user.
- **Non-blocking:** fix, or defer with a reason and revisit trigger.
- **Nit:** fix when practical and in scope, otherwise defer with a reason.

Record each finding as validated or not, with evidence and a disposition, and report deferred findings to the user. After non-trivial fixes or rollback, rerun gates and ask the same reviewer to review the delta, affected behavior and unresolved findings; a substantial redesign needs a full review. Purely editorial follow-ups (comments, docstrings, Markdown prose) MAY keep the prior verdict when they cannot affect execution or tests; directive comments such as `# type:` or `# noqa` are not editorial. Completion requires no unresolved Blocking finding and a disposition for every finding; `Review blocked` is not a pass.

## Report

The reviewer writes a section in the working record (or a separate report if requested). A clean review still states its verification and verdict. Follow-ups may cover only the delta, new verification, finding updates and the revised verdict.

```markdown
## Adversarial Review Report

**Target:** <candidate and scope; prior target for follow-ups>
**Reviewer:** <session ID, model/effort>
**Verification:** <what was read, probes and mutants run, results>
**Assumptions and limitations:** <material qualifications>
**Cleanup:** <owned scratch/process cleanup, or none created>

### Findings

1. **Blocking | Non-blocking | Nit** — `path:line`: <defect, evidence, impact; optional remedy>

### Verdict

<No blocking findings | N blocking findings — fix and re-review | Review blocked — reason>
```

The main agent appends the snapshot comparison result and each finding's validation and disposition without altering the reviewer's section. Only the reviewer changes classifications or the verdict.
