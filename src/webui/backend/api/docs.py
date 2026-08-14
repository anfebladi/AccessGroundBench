"""Doc endpoints -- lets the UI show a project markdown doc in a modal
instead of just naming it in prose (e.g. "See docs/collection.md").

Read-only, and restricted to a fixed allowlist of filenames rather than
joining `name` onto a path, so this cannot be used to read arbitrary files.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

import paths

router = APIRouter()

#: Every doc the UI is allowed to fetch and render. Keyed by the name the
#: frontend asks for, which today is just the filename under docs/.
ALLOWED_DOCS = {
    "collection.md",
    "setup.md",
    "cli-reference.md",
    "troubleshooting.md",
    "methods.md",
    "ui.md",
    "ui-design-system.md",
    "ferret-ui.md",
    "9router.md",
}


@router.get("/api/docs/{name}")
def get_doc(name: str) -> dict:
    if name not in ALLOWED_DOCS:
        raise HTTPException(status_code=404, detail=f"Unknown doc: {name}")
    doc_path = paths.PROJECT_ROOT / "docs" / name
    if not doc_path.is_file():
        raise HTTPException(status_code=404, detail=f"Missing doc file: {name}")
    return {"name": name, "content": doc_path.read_text(encoding="utf-8")}


__all__ = ["router"]
