"""Domain logic behind the web UI's API -- no HTTP knowledge.

Nothing in this package may import fastapi. These modules are the layer the
route handlers in ..api call into, and they stay callable from a plain test or
script with the optional `ui` extra uninstalled. Raising HTTPException, reading
request bodies, and validating query parameters all belong in ..api instead.

Deliberately not a re-exporting facade: .analysis_tables reaches the analysis
layer and .compare reaches both analysis and evaluation, each behind a
function-level import. Importing their names here would make those costs
unavoidable for every caller that only wanted, say, the session key store.
"""
