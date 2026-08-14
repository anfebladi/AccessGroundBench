"""The HTTP layer: one router module per route family, plus its request
schemas and per-request helpers.

This is the only part of webui.backend that knows about HTTP. Route handlers
here validate input and raise HTTPException; the domain work they delegate to
lives in ..services, which must stay importable without fastapi.

These modules import fastapi at module scope -- an APIRouter has to exist
before its decorators can run. That is safe because nothing imports this
package unless server.create_app() is being called, which already requires the
optional `ui` extra.

Route families are registered in server.create_app(). Ordering between routers
does not matter (no two declare overlapping paths); ordering *within*
api.results does -- see its module docstring.
"""

from __future__ import annotations

from . import analysis, collect, datasets, docs, evaluate, models, results

#: Included by server.create_app() in this order.
ALL_ROUTERS = (
    datasets.router,
    results.router,
    analysis.router,
    evaluate.router,
    models.router,
    collect.router,
    docs.router,
)

__all__ = [
    "ALL_ROUTERS", "analysis", "collect", "datasets", "docs", "evaluate", "models", "results",
]
