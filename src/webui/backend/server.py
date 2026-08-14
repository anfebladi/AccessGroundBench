"""FastAPI application factory for the AccessGroundBench local UI.

This module builds the API and nothing else. The routes themselves live in
.api, one module per route family; the processes that serve them -- the
uvicorn thread, the Vite child, the terminal menu -- belong to .launcher, which
is what `agb ui` actually calls.

The server is bound to 127.0.0.1 only, always -- not configurable (see
.launcher). Session API keys live in this process's memory (see
.services.keys), so it must never accept connections from beyond localhost.
"""

from __future__ import annotations


def create_app():
    """Build the API.

    Importing this module does not require the optional `ui` extra; calling
    this function does. Hence the imports below, and .api being imported here
    rather than at module scope.
    """
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    from .api import ALL_ROUTERS

    app = FastAPI(title="AccessGroundBench UI")

    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def _flatten_validation_error(request, exc: RequestValidationError) -> JSONResponse:
        """Return a request-validation failure with a *string* `detail`.

        FastAPI's default makes `detail` a list of error objects, but the
        frontend's ApiError (frontend/src/lib/api.ts) reads `detail` and renders
        it directly -- a list reaches the user as "[object Object]". Flattening
        here keeps every error response in this API the same shape as the
        hand-written HTTPException ones.
        """
        parts = []
        for err in exc.errors():
            field = ".".join(str(p) for p in err.get("loc", ()) if p != "body")
            message = err.get("msg", "invalid value")
            parts.append(f"{field}: {message}" if field else message)
        return JSONResponse(
            status_code=422,
            content={"detail": "; ".join(parts) or "Invalid request body"},
        )

    return app


__all__ = ["create_app"]
