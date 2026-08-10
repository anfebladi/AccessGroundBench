"""Local web UI for AccessGroundBench.

Kept optional at the package level: nothing else in the codebase imports
`webui`, so `fastapi`/`uvicorn` are only required when a user actually runs
`agb ui` (see the [project.optional-dependencies].ui extra in pyproject.toml
and the lazy import in cli.py's COMMANDS table).
"""
