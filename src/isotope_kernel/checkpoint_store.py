"""Opaque checkpoint storage boundary for the Isotope v0.1 slice."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any


class FileCheckpointStore:
    """Run-scoped checkpoint blob store.

    This class only validates the storage boundary. It does not interpret
    projected state semantics and does not participate in event log replay.
    """

    REQUIRED_FIELDS = {"run_id", "projector_version", "basis_event_id", "state", "created_at"}
    FORBIDDEN_RAW_KEYS = {"raw_input", "provider_response", "imported_snapshot"}

    def __init__(self, root: Path):
        self.root = Path(root)

    def checkpoint_path(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.root / "runs" / run_id / "checkpoints" / "latest.json"

    def save_checkpoint(self, run_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        self._validate_run_id(run_id)
        self._validate_checkpoint(run_id, checkpoint)
        path = self.checkpoint_path(run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(checkpoint, sort_keys=True), encoding="utf-8")
        return checkpoint

    def save_checkpoint_history(self, run_id: str, checkpoint: dict[str, Any]) -> dict[str, Any]:
        self._validate_run_id(run_id)
        self._validate_checkpoint(run_id, checkpoint)
        path = self._history_checkpoint_path(run_id, checkpoint)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(checkpoint, sort_keys=True), encoding="utf-8")
        return checkpoint

    def load_latest_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        self._validate_run_id(run_id)
        path = self.checkpoint_path(run_id)
        if not path.exists():
            return None
        return self._load_checkpoint_file(run_id, path)

    def load_checkpoint_candidates(self, run_id: str) -> list[dict[str, Any]]:
        self._validate_run_id(run_id)
        checkpoint_dir = self.root / "runs" / run_id / "checkpoints"
        if not checkpoint_dir.exists():
            return []

        candidates = [
            self._load_checkpoint_file(run_id, path)
            for path in sorted(checkpoint_dir.glob("*.json"))
            if path.is_file()
        ]
        return sorted(
            candidates,
            key=lambda checkpoint: str(checkpoint.get("created_at", "")),
            reverse=True,
        )

    def _load_checkpoint_file(self, run_id: str, path: Path) -> dict[str, Any]:
        try:
            checkpoint = json.loads(path.read_text(encoding="utf-8"))
        except JSONDecodeError as exc:
            raise ValueError(f"malformed checkpoint file: {path}") from exc
        if not isinstance(checkpoint, dict):
            raise ValueError(f"malformed checkpoint file: {path}")
        try:
            self._validate_checkpoint(run_id, checkpoint)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"malformed checkpoint file: {path}") from exc
        return checkpoint

    def _history_checkpoint_path(self, run_id: str, checkpoint: dict[str, Any]) -> Path:
        checkpoint_dir = self.root / "runs" / run_id / "checkpoints"
        created_at = self._safe_filename_part(checkpoint["created_at"])
        basis_event_id = self._safe_filename_part(checkpoint["basis_event_id"])
        return checkpoint_dir / f"checkpoint-{created_at}-{basis_event_id}.json"

    def _safe_filename_part(self, value: Any) -> str:
        safe = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in str(value)
        ).strip("._-")
        if not safe or safe in {".", ".."}:
            return "value"
        return safe

    def _validate_checkpoint(self, run_id: str, checkpoint: dict[str, Any]) -> None:
        if not isinstance(checkpoint, dict):
            raise TypeError("checkpoint must be a dict")

        for field in sorted(self.REQUIRED_FIELDS):
            if field not in checkpoint:
                raise ValueError(f"checkpoint missing required field: {field}")

        if checkpoint["run_id"] != run_id:
            raise ValueError("checkpoint run_id must match save run_id")

        for key in sorted(self.FORBIDDEN_RAW_KEYS):
            if key in checkpoint:
                raise ValueError(f"checkpoint cannot contain external raw input: {key}")

    def _validate_run_id(self, run_id: str) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("run_id must be a non-empty path segment")
        if run_id in {".", ".."} or "/" in run_id or "\\" in run_id:
            raise ValueError("run_id must be a safe path segment")
