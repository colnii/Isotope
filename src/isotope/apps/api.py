"""Thin API application boundary over the in-process HTTP facade."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qs

from ..interfaces.http import create_http_app

AsgiReceive = Callable[[], Awaitable[dict[str, Any]]]
AsgiSend = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass(frozen=True)
class ApiAppConfig:
    root_path: Path
    allow_artifact_content: bool = False


class ApiApp:
    """ASGI-compatible app boundary for product HTTP routes."""

    def __init__(self, config: ApiAppConfig):
        self.config = config
        self.http_app = create_http_app(
            config.root_path,
            allow_artifact_content=config.allow_artifact_content,
        )

    def routes(self) -> list[tuple[str, str]]:
        return self.http_app.routes()

    def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ):
        return self.http_app.request(method, path, json=json_body)

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        if scope.get("type") != "http":
            await self._send_json(
                send,
                500,
                {"status": "error", "error": {"code": "unsupported_scope"}},
            )
            return
        body = await _read_body(receive)
        try:
            json_body = _merge_query_params(
                _decode_json_body(body),
                _decode_query_params(scope.get("query_string", b"")),
            )
        except ValueError as exc:
            await self._send_json(
                send,
                400,
                {
                    "status": "error",
                    "error": {
                        "code": "invalid_json",
                        "message": str(exc),
                    },
                },
            )
            return
        response = self.http_app.request(
            str(scope.get("method", "GET")),
            str(scope.get("path", "/")),
            json=json_body,
        )
        await self._send_json(send, response.status_code, response.body)

    async def _send_json(
        self,
        send: AsgiSend,
        status_code: int,
        body: dict[str, Any] | list[dict[str, Any]],
    ) -> None:
        payload = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": (
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"x-isotope-api", b"asgi"),
                ),
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": payload,
                "more_body": False,
            }
        )


def create_api_app(
    root_path: Path | str,
    *,
    allow_artifact_content: bool = False,
) -> ApiApp:
    return ApiApp(
        ApiAppConfig(
            root_path=Path(root_path),
            allow_artifact_content=allow_artifact_content,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect the Isotope API app.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    routes_parser = subparsers.add_parser("routes", help="List supported API routes.")
    routes_parser.add_argument("--root", required=True, help="Runtime root directory.")
    routes_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    request_parser = subparsers.add_parser(
        "request",
        help="Invoke a local API route through the in-process HTTP facade.",
    )
    request_parser.add_argument("--root", required=True, help="Runtime root directory.")
    request_parser.add_argument("method", help="HTTP method, for example GET or POST.")
    request_parser.add_argument("path", help="API path, for example /health.")
    request_parser.add_argument(
        "--body-json",
        help="JSON object body to send with the request.",
    )
    request_parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    app = create_api_app(args.root)
    if args.command == "routes":
        payload = {
            "status": "ok",
            "routes": [
                {"method": method, "path": path}
                for method, path in app.routes()
            ],
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            for route in payload["routes"]:
                print(f"{route['method']} {route['path']}")
        return 0
    if args.command == "request":
        try:
            body = _decode_cli_json_body(args.body_json)
        except ValueError as exc:
            parser.error(str(exc))
        response = app.request(args.method, args.path, body)
        payload = {
            "status_code": response.status_code,
            "body": response.body,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        else:
            print(f"status_code: {response.status_code}")
            print(json.dumps(response.body, ensure_ascii=False, sort_keys=True))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


async def _read_body(receive: AsgiReceive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            return b"".join(chunks)


def _decode_json_body(body: bytes) -> dict[str, Any] | None:
    if not body:
        return None
    try:
        decoded = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("request body must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("request body must be a JSON object")
    return decoded


def _decode_cli_json_body(raw_body: str | None) -> dict[str, Any] | None:
    if raw_body is None:
        return None
    try:
        decoded = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError("--body-json must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise ValueError("--body-json must be a JSON object")
    return decoded


def _decode_query_params(raw_query_string: Any) -> dict[str, Any]:
    if isinstance(raw_query_string, str):
        query_string = raw_query_string
    elif isinstance(raw_query_string, bytes):
        query_string = raw_query_string.decode("utf-8")
    else:
        query_string = ""
    if not query_string:
        return {}
    parsed = parse_qs(query_string, keep_blank_values=False)
    return {
        key: _coerce_query_value(key, values)
        for key, values in parsed.items()
    }


def _coerce_query_value(key: str, values: list[str]) -> str | int | list[str | int]:
    coerced = [_coerce_query_scalar(value) for value in values]
    if key in {"types"}:
        return coerced
    if len(coerced) == 1:
        return coerced[0]
    return coerced


def _coerce_query_scalar(value: str) -> str | int:
    if value.isdecimal():
        return int(value)
    return value


def _merge_query_params(
    json_body: dict[str, Any] | None,
    query_params: dict[str, Any],
) -> dict[str, Any] | None:
    if not query_params:
        return json_body
    merged = dict(query_params)
    if json_body is not None:
        merged.update(json_body)
    return merged


if __name__ == "__main__":
    raise SystemExit(main())
