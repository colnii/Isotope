"""Desktop artifact content routes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from isotope.workspace.artifacts import ArtifactStore


def desktop_screen_artifact_content_id(path: str) -> str | None:
    prefix = "/desktop/artifacts/"
    suffix = "/screen-content"
    if not path.startswith(prefix) or not path.endswith(suffix):
        return None
    artifact_id = unquote(path[len(prefix) : -len(suffix)])
    if "/" in artifact_id or not artifact_id:
        return None
    return artifact_id


def screen_screenshot_artifact_payload(root: Path, artifact_id: str) -> dict[str, Any]:
    store = ArtifactStore(root)
    artifact = store.get_metadata(artifact_id, include_provenance=True)
    if artifact.get("artifact_type") != "screen_screenshot":
        raise ValueError("artifact is not a screen_screenshot")
    artifact_path = _artifact_file_for_id(root, artifact_id)
    if artifact_path is None:
        raise FileNotFoundError(f"artifact not found: {artifact_id}")
    try:
        image = json.loads(store.get_content(artifact_id))
    except json.JSONDecodeError as exc:
        raise ValueError("screen screenshot artifact content is malformed") from exc
    if not isinstance(image, dict):
        raise ValueError("screen screenshot artifact content must be an object")
    if image.get("encoding") != "base64":
        raise ValueError("screen screenshot artifact must use base64 encoding")
    media_type = image.get("media_type")
    data = image.get("data")
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        raise ValueError("screen screenshot artifact media_type must be an image")
    if not isinstance(data, str) or not data:
        raise ValueError("screen screenshot artifact data must be non-empty")
    return {
        "artifact": {
            "artifactType": artifact["artifact_type"],
            "summary": artifact["summary"],
            "ref": _artifact_ref_for_path(root, artifact_path, artifact_id),
            "provenance": artifact.get("provenance", {}),
        },
        "image": {
            "mediaType": media_type,
            "width": image.get("width"),
            "height": image.get("height"),
            "data": data,
            "dataUrl": f"data:{media_type};base64,{data}",
        },
        "file": {
            "path": str(artifact_path),
            "directory": str(artifact_path.parent),
            "downloadFilename": f"{artifact_id}.{_image_extension(media_type)}",
        },
    }


def _artifact_file_for_id(root: Path, artifact_id: str) -> Path | None:
    matches = sorted((root / "runs").glob(f"*/artifacts/{artifact_id}.json"))
    return matches[0] if matches else None


def _artifact_ref_for_path(root: Path, artifact_path: Path, artifact_id: str) -> dict[str, str]:
    try:
        run_id = artifact_path.relative_to(root).parts[1]
    except (ValueError, IndexError):
        run_id = ""
    return {
        "ref_type": "artifact",
        "scope": "run",
        "run_id": run_id,
        "artifact_id": artifact_id,
    }


def _image_extension(media_type: str) -> str:
    if media_type == "image/jpeg":
        return "jpg"
    if media_type == "image/png":
        return "png"
    return media_type.removeprefix("image/").replace("+xml", "") or "img"
