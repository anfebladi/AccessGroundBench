## Project context

- `agb` is the unified command dispatcher. The main source areas are `src/collection`, `src/evaluation`, and `src/analysis`; the Ferret UI lives in `ferret_ui`, tests live in `tests`, local inputs and outputs in `dataset`, and operator documentation in `docs`.
- Development uses Python 3.11 or newer. Install with `uv sync`; prefer the `agb` command and the CLI reference when documenting or invoking workflows.

## Workflow and safety

- Run the full test suite with `uv run python -m unittest discover -s tests -p "test_*.py"`; for behavior changes, also run the narrowest relevant tests. For documentation-only edits, run `git diff --check`.
- Do not produce diabolical one-line code: when code contains nested logic, multiple operations, complex data, or substantial markup, format it across clear, readable lines with sensible indentation. One-line code is acceptable only when it remains obviously simple.
- Treat `.env` as sensitive: never add credentials, and do not change the selected model or provider implicitly. `agb evaluate` calls external providers, may incur cost, resumes through a lock by default, and `--fresh` discards and recreates the result CSV.
- `agb collect`, `agb profile`, and `agb capture` mutate emulator state or captures; require explicit user authorization and preserve/reset a known baseline. `agb analyze` rewrites reports. `agb canonicalize` and non-check `agb rescore` rewrite CSVs with backups; `agb rescore --check` is read-only.
- `agb collect --rebuild-manifest` works offline from existing assets but overwrites/merges the manifest for selected records while preserving other existing records. The archived `dataset/experiment_2` is historical and must not be cited as current evidence. There is no current RTL profile.

## Main orchestrator

- The primary agent coordinates delegated work by default.
- For each delegation, assign exact files or bounded ownership, allowed edit types, expected outcome, and dependencies.
- Keep one editing owner per file or bounded code area.
- Do not assign overlapping files, shared tests, or cross-cutting contracts to concurrent editing workers.
- The orchestrator plan is the source of truth for whether `code-writer`, `test-writer`, `test-worker`, or another worker is needed, and for their ordering. Update the plan when implementation findings change the required coverage or verification.
- The orchestrator reconciles worker results, verifies material findings, and reports delegated work plus exact checks run and results.
- Before the primary agent edits workspace files directly, ask the user for approval.
- In Plan Mode, record the proposed direct edit in the plan and request approval before execution.
- Outside Plan Mode, ask before the direct edit.
- Run workers in parallel only when their scopes are independent. All worker conditions, ownership rules, ordering, and verification requirements still apply.
- Start test writing, documentation, or reviews alongside implementation only when their inputs are stable enough; otherwise wait for the required dependency.
- Run dependent verification only after the relevant implementation and test-writing workers finish.
- If a worker detects overlap, a blocked dependency, or work outside its scope, it must stop and report back to the orchestrator.

### explorer-worker

- Invoke `explorer-worker` before ordinary code changes for focused, read-only repository exploration.
- Limit exploration to task-relevant files and request a concise implementation map with important paths, dependencies, conventions, and risks.
- The worker must not modify files.

### code-writer

- Invoke one `code-writer` as the default implementation owner for an assigned source area.
- Assign only the source files and implementation configuration it may edit; do not assign tests, documentation, or another worker's files unless explicitly intended.
- The worker reports changed files, behavior, checks run, assumptions, and remaining risks.

### test-writer

- Invoke `test-writer` when the approved orchestrator plan identifies changed behavior, missing coverage, regression risk, or a test-only change that requires new or revised tests. Do not invoke it for documentation-only changes unless the plan explicitly calls for test updates.
- Run it after exploration and once the affected behavior or test contract is stable. It may run alongside `code-writer` only when the plan gives it a disjoint test-only ownership area and the required interfaces are stable.
- Assign only relevant test files and fixtures. The worker must not modify source, configuration, migrations, or documentation.
- The worker adds focused, deterministic tests and reports the cases covered.

### test-worker

- Invoke `test-worker` according to the approved orchestrator plan after the relevant `code-writer` and/or `test-writer` work completes. For source changes, run the narrowest relevant checks after implementation and planned test writing; for test-only changes, run them after `test-writer` completes.
- For documentation-only changes, use `git diff --check` and do not invoke `test-worker` unless the plan explicitly requires a verification run.
- The worker is read-only and must not fix failures or modify files.
- The worker reports exact commands, results, and important errors.

### redundancy-worker

- Invoke `redundancy-worker` after refactoring, consolidation, migration, reorganization, or meaningful code deletion.
- Limit review to the changed paths and current diff. The worker must not modify files.
- Treat its output as review feedback; address only findings supported by evidence and relevant to the requested work.

### docs-worker

- Invoke `docs-worker` only when behavior, APIs, setup, configuration, architecture, deployment, or operations change.
- Assign only directly related documentation files. The worker must not modify application code, tests, migrations, or configuration.
- The worker reports documentation files changed and summarizes each update.

## Documentation authority

Keep durable guidance in the canonical documents below; link to them instead of duplicating command specifications:

- [Setup](docs/setup.md) — installation, environment, and emulator preparation.
- [CLI reference](docs/cli-reference.md) — `agb` command syntax and effects.
- [Collection guide](docs/collection.md) and [collection runbook](docs/runbooks/collection.md) — capture reference and live operator procedure.
- [Evaluation runbook](docs/runbooks/evaluation.md) — evaluating existing captures and reporting.
- [Ferret UI](docs/ferret-ui.md) — Ferret setup and operation.
- [Troubleshooting](docs/troubleshooting.md) — common failures and recovery.
- [Methods](docs/methods.md) — analysis methodology and interpretation.
- [CLAUDE.md](CLAUDE.md) — architecture, invariants, and current project status.

Update this guide when public behavior, configuration, operations, or methodology changes; keep detailed command specs in the CLI reference and avoid duplicating them here.
