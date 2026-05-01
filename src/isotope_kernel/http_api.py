"""In-process HTTP API boundary for the v0.2 minimal surface.

This module is a test-client style facade. It does not open sockets and does
not commit the project to a web framework.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .server import InProcessServer


@dataclass(frozen=True)
class HttpResponse:
    """Small response shape for in-process API tests."""

    status_code: int
    body: dict[str, Any] | list[dict[str, Any]]

    def json(self) -> dict[str, Any] | list[dict[str, Any]]:
        return self.body


class HttpApiApp:
    """Minimal in-process HTTP-like app for the kernel runtime boundary."""

    _ROUTES: tuple[tuple[str, str], ...] = (
        ("POST", "/sessions"),
        ("POST", "/sessions/{session_id}/runs"),
        ("POST", "/runs/{run_id}/input"),
        ("GET", "/runs/{run_id}"),
        ("GET", "/runs/{run_id}/events"),
        ("GET", "/artifacts/{artifact_id}/summary"),
        ("GET", "/health"),
    )

    def __init__(self, root_path: Path | str):
        self.root_path = Path(root_path)
        self.server = InProcessServer(self.root_path)

    def routes(self) -> list[tuple[str, str]]:
        return list(self._ROUTES)

    def request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> HttpResponse:
        method = method.upper()
        parts = self._split_path(path)
        body = json if json is not None else {}

        try:
            if method == "GET" and parts == ["health"]:
                return self._json(200, {"status": "ok"})
            if method == "POST" and parts == ["sessions"]:
                return self._json(201, self.server.create_session())
            if method == "POST" and len(parts) == 3 and parts[0] == "sessions" and parts[2] == "runs":
                return self._json(
                    201,
                    self.server.create_run(parts[1], goal=str(body.get("goal", "default goal"))),
                )
            if method == "POST" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "input":
                result = self.server.submit_input(parts[1], text=str(body.get("text", "")))
                return self._json(200, self._submit_result_to_dict(result))
            if method == "GET" and len(parts) == 2 and parts[0] == "runs":
                return self._json(200, self._run_state_to_dict(self.server.get_run_state(parts[1])))
            if method == "GET" and len(parts) == 3 and parts[0] == "runs" and parts[2] == "events":
                return self._json(200, [event.to_dict() for event in self.server.get_events(parts[1])])
            if method == "GET" and len(parts) == 3 and parts[0] == "artifacts" and parts[2] == "summary":
                summary = self._find_artifact_summary(parts[1])
                if summary is None:
                    return self._json(404, {"status": "not_found"})
                return self._json(200, summary)
        except PermissionError as exc:
            return self._json(403, {"status": "forbidden", "error": str(exc)})
        except (FileNotFoundError, ValueError) as exc:
            return self._json(400, {"status": "bad_request", "error": str(exc)})

        return self._json(404, {"status": "not_found"})

    def _find_artifact_summary(self, artifact_id: str) -> dict[str, Any] | None:
        runs_root = self.root_path / "runs"
        if not runs_root.exists():
            return None
        for event_path in sorted(runs_root.glob("*/events.jsonl")):
            run_id = event_path.parent.name
            for event in self.server.event_store.list_events(run_id):
                if event.event_type != "artifact.created":
                    continue
                artifact = event.payload.get("artifact")
                if not isinstance(artifact, dict):
                    continue
                ref = artifact.get("ref")
                if not isinstance(ref, dict) or ref.get("artifact_id") != artifact_id:
                    continue
                return {
                    "ref": dict(ref),
                    "artifact_type": artifact["artifact_type"],
                    "summary": artifact["summary"],
                    "provenance": dict(artifact["provenance"]),
                }
        return None

    def _submit_result_to_dict(self, result: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "status": result["status"],
            "run_state": self._run_state_to_dict(result["run_state"]),
        }
        artifact_ref = result.get("artifact_ref")
        if artifact_ref is not None:
            body["artifact_ref"] = artifact_ref.to_dict()
        if result.get("execution_id"):
            body["execution_id"] = result["execution_id"]
        return body

    def _run_state_to_dict(self, state: Any) -> dict[str, Any]:
        return asdict(state)

    def _json(
        self,
        status_code: int,
        body: dict[str, Any] | list[dict[str, Any]],
    ) -> HttpResponse:
        return HttpResponse(status_code=status_code, body=body)

    def _split_path(self, path: str) -> list[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            return []
        return [part for part in path.split("/") if part]


def create_http_app(root_path: Path | str) -> HttpApiApp:
    return HttpApiApp(root_path=root_path)
