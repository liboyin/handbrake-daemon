# Scratch Testing Recipe

Use this recipe whenever the [review procedure](../SKILL.md#procedure) or an implementer runs tests or mutants against a candidate outside the main working tree. Reading source and diffs needs no scratch copy. AGENTS' [test-ownership rules](../../../../AGENTS.md#tests) still apply inside scratch.

## Copy

Create one owned scratch directory outside the repository per agent and candidate; never share a writable scratch tree between agents. From the repository root, copy the tracked working tree plus only the explicitly named in-scope untracked files, preserving modes and copying symlinks as links:

```bash
git ls-files -z | xargs -0 cp --parents -P -p -t "$SCRATCH"
cp --parents -P -p -t "$SCRATCH" -- <in-scope untracked files>
```

Tracked files deleted but not yet staged in the candidate are reported missing and make the first command exit non-zero; confirm those are the only errors. Never copy `.git`, ignored files, `.env`, credentials, `assets/` or other host data. The only expected symlink, `.claude/skills`, points inside the copy; if a candidate adds a link whose target leaves scratch, do not follow it, and return `Review blocked` if the target is required. Restore the candidate before each mutant, and use fresh test processes.

## Run and verify provenance

The devcontainer installs the package in editable mode, through an import finder that maps `handbrake_daemon` to the original repository. A scratch run without `PYTHONPATH` pointing at the scratch root falls through to that finder and silently tests the original code, so every mutant appears to survive. Because `PROJECT_ROOT` derives from the imported module's location, such a run also resolves the default `MONITOR_DIR` to the real `assets/` mount. Verify inside the pytest process that the exercised modules came from scratch by adding this hook to scratch's `tests/conftest.py` only (create it if absent; never add it to the repository). List the modules the selected tests exercise:

```python
from pathlib import Path
import sys

import pytest


def pytest_sessionfinish(session, exitstatus):
    """Verify exercised application provenance without preloading application modules."""
    scratch_root = Path(__file__).resolve().parents[1]
    names = ("handbrake_daemon.__main__",)
    for name in names:
        module = sys.modules.get(name)
        if module is None:
            raise pytest.UsageError(f"Expected exercised module is absent: {name}")
        location = Path(module.__file__).resolve()
        if not location.is_relative_to(scratch_root):
            raise pytest.UsageError(f"Application import escaped scratch: {name}: {location}")
    print(f"ACTUAL_IMPORT_PROVENANCE scratch={scratch_root} verified={','.join(names)}")
```

Then run fresh processes from the scratch root, with temporary files inside it:

```bash
mkdir -p owned-temp
PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 TMPDIR="$PWD/owned-temp" python -m pytest tests/test_main.py --no-cov -p no:cacheprovider --basetemp="$PWD/owned-temp/pytest"
```

A valid run prints an `ACTUAL_IMPORT_PROVENANCE` line; an escaped import makes pytest exit with status 4. `--no-cov` and `-p no:cacheprovider` avoid reports and caches for focused probes; final gates keep the configured coverage reporting. Note pytest-randomly's seed for reproduction.

## Mutation evidence

First run the selected tests unmutated, with the same command and hook, and confirm they pass. Choose mutants by protected invariant, not by count, and make each mutant perform the risky side effect (for example, actually delete or overwrite an output that should be kept, or select a file that is still being written) rather than merely prepare it. Before running, confirm that every path the mutant can reach, including outputs, temporary outputs and rename destinations, is owned by the test, even if the mutant bypasses validation. Also confirm the mutant cannot run HandBrakeCLI or `nvidia-smi`: both are installed in the devcontainer, so a mutant that bypasses a mock really runs them.

A kill needs a relevant behavioral assertion failure. Collection, syntax, import and environment errors, or a failed provenance check, make the run invalid: neither a kill nor a survivor. If a run escapes ownership, stop it and any owned work, restore the candidate, and fix containment before retrying; never repeat the unsafe command unchanged. Investigate a surviving mutant before concluding coverage is missing.

Whoever produces required evidence (normally the implementer; the reviewer checks it and fills gaps) records in the working record, per invariant: the candidate identity, mutant diff, selected test, exact command and seed, provenance line and relevant failure excerpt. Record invalid runs separately. Full passing logs and repeated tracebacks are unnecessary. Rerun affected cases when the candidate, mutant or selected tests change.

## Cleanup

Save essential evidence outside scratch, then delete the scratch directory and stop any owned processes.
