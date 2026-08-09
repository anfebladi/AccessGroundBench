## Main orchestrator

- The primary agent coordinates delegated work by default.
- For each delegation, assign exact files or bounded ownership, allowed edit types, expected outcome, and dependencies.
- Keep one editing owner per file or bounded code area.
- Do not assign overlapping files, shared tests, or cross-cutting contracts to concurrent editing workers.
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

- Invoke `test-writer` only when the approved plan identifies changed behavior, missing coverage, or regression risk.
- Assign only relevant test files and fixtures. The worker must not modify source, configuration, migrations, or documentation.
- The worker adds focused, deterministic tests and reports the cases covered.

### test-worker

- Invoke `test-worker` after source-code changes to run the narrowest relevant checks.
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
