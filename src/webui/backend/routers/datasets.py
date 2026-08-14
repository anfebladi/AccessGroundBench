"""Dataset browsing endpoints -- what the Dataset view reads.

Everything here is a read of a dataset's own files on disk: the registry, the
screen list, harvested targets, and the raw image/label/manifest artefacts.
Nothing in this router writes, runs, or spawns anything.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import datasets as datasets_mod
from ..dependencies import baseline_screens, dataset_or_404
from ..stdout_capture import capture_stdout

router = APIRouter()


@router.get("/api/datasets")
def list_datasets() -> list[dict]:
    return [d.to_dict() for d in datasets_mod.discover_datasets()]


@router.get("/api/datasets/{name}/screens")
def dataset_screens(name: str) -> dict:
    info = dataset_or_404(name)
    return {"screens": baseline_screens(info.path / "labels")}


@router.get("/api/datasets/{name}/targets/{screen}")
def dataset_targets(name: str, screen: str) -> dict:
    from evaluation.grounding.targets import harvest_targets

    info = dataset_or_404(name)
    with capture_stdout():
        targets = harvest_targets(screen, info.path / "labels")
    return {"targets": targets}


@router.get("/api/datasets/{name}/image/{screen}/{profile}")
def dataset_image(name: str, screen: str, profile: str):
    info = dataset_or_404(name)
    image_path = info.path / "images" / f"{screen}_{profile}.png"
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail=f"No image: {image_path.name}")
    return FileResponse(image_path, media_type="image/png")


@router.get("/api/datasets/{name}/labels/{screen}/{profile}")
def dataset_labels(name: str, screen: str, profile: str) -> list[dict]:
    info = dataset_or_404(name)
    label_path = info.path / "labels" / f"{screen}_{profile}.json"
    if not label_path.is_file():
        raise HTTPException(status_code=404, detail=f"No labels: {label_path.name}")
    return json.loads(label_path.read_text(encoding="utf-8"))


@router.get("/api/datasets/{name}/manifest")
def dataset_manifest(name: str) -> dict:
    info = dataset_or_404(name)
    manifest_path = info.path / "collection_manifest.json"
    if not manifest_path.is_file():
        return {"available": False}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {"available": True, "manifest": data}


__all__ = ["router"]
