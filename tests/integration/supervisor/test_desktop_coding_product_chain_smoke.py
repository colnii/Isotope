from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path
from typing import Any

from isotope.features.supervisor.web import create_dashboard_server
from isotope.interfaces.http import create_http_app
from isotope.llm.provider import LLMResponse


class CodingProductChainProvider:
    provider = "deterministic_coding_product_chain"
    model = "stub-coding-product-chain"

    def __init__(self) -> None:
        patch = (
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1,2 +1,3 @@\n"
            " def answer():\n"
            "-    return 'old desktop value'\n"
            "+    value = 'new desktop value'\n"
            "+    return value\n"
        )
        self.responses = [
            _decision(
                "code.search",
                {
                    "query": "old desktop value",
                    "include_paths": ["src"],
                    "max_results": 5,
                },
            ),
            _decision(
                "code.read",
                {
                    "path": "src/app.py",
                    "max_excerpt_chars": 500,
                },
            ),
            _decision(
                "code.apply_patch",
                {
                    "patch": patch,
                },
            ),
            _decision(
                "artifact.diff_result",
                {
                    "workspace_id": "desktop_code_workspace",
                    "run_id": "run_desktop_code",
                    "execution_id": "exec_desktop_code_diff",
                    "include_paths": ["src"],
                },
            ),
            json.dumps(
                {
                    "kind": "direct_answer",
                    "answer": "已修改 src/app.py，并生成 diff result artifact。",
                    "rationale": "The coding observations and artifact summary are available.",
                }
            ),
        ]
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 512,
    ) -> LLMResponse:
        self.calls.append({"messages": messages, "max_tokens": max_tokens})
        return LLMResponse(
            provider=self.provider,
            model=self.model,
            content=self.responses.pop(0),
            finish_reason="stop",
            usage={},
            raw={"raw_response": "must not leak"},
        )


def test_desktop_chat_can_drive_search_read_patch_and_diff_artifact(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    _seed_workspace(workspace)
    state_root = tmp_path / "state"
    _seed_materialized_baseline(state_root)
    provider = CodingProductChainProvider()
    server = create_dashboard_server(
        codex_home=state_root,
        host="127.0.0.1",
        port=0,
        limit=5,
        stale_after_seconds=999999,
        active_within_seconds=180,
        desktop_chat_provider=provider,
    )

    response, body = _post_desktop_chat(
        server,
        {
            "question": "把 src/app.py 里的 old desktop value 改成 new desktop value，并给我 diff 摘要。",
            "workspace_cwd": str(workspace),
        },
    )

    assert response.status == 200
    events = _parse_sse(body)
    assert [event["event"] for event in events] == [
        "start",
        "capacity_start",
        "capacity_result",
        "capacity_start",
        "capacity_result",
        "capacity_start",
        "capacity_result",
        "capacity_start",
        "capacity_result",
        "delta",
        "done",
    ]
    capacity_results = [
        event["data"] for event in events if event["event"] == "capacity_result"
    ]
    assert [result["capacity_id"] for result in capacity_results] == [
        "code.search",
        "code.read",
        "code.apply_patch",
        "artifact.diff_result",
    ]
    assert [result["status"] for result in capacity_results] == ["ok", "ok", "ok", "ok"]
    code_search_detail = _detail_content(capacity_results[0], "Code search result")
    assert code_search_detail["matches"][0]["path"] == "src/app.py"
    assert code_search_detail["matches"][0]["excerpt"].strip() == (
        "return 'old desktop value'"
    )
    code_read_detail = _detail_content(capacity_results[1], "Code read result")
    assert code_read_detail["path"] == "src/app.py"
    assert "def answer" in code_read_detail["excerpt"]
    patch_detail = _detail_content(capacity_results[2], "Patch result")
    assert patch_detail["changed_files"] == ["src/app.py"]
    assert patch_detail["file_count"] == 1
    diff_detail = _detail_content(capacity_results[3], "Artifact result")
    assert diff_detail["artifact_type"] == "native_coding.diff_result"
    assert diff_detail["summary"] == "1 changed file in desktop_code_workspace"
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == (
        "def answer():\n"
        "    value = 'new desktop value'\n"
        "    return value\n"
    )

    second_call = json.dumps(provider.calls[1]["messages"], ensure_ascii=False)
    third_call = json.dumps(provider.calls[2]["messages"], ensure_ascii=False)
    fourth_call = json.dumps(provider.calls[3]["messages"], ensure_ascii=False)
    final_call = json.dumps(provider.calls[4]["messages"], ensure_ascii=False)
    assert "code_search" in second_call
    assert "src/app.py" in second_call
    assert "old desktop value" in second_call
    assert "code_read" in third_call
    assert "def answer" in third_call
    assert "patch_result" in fourth_call
    assert "changed_files" in fourth_call
    assert "raw_response" not in final_call
    assert "--- a/src/app.py" not in final_call

    loop_artifact_id = capacity_results[-1]["result"]["agent_loop_artifact_id"]
    loop_content_app = create_http_app(
        state_root / "supervisor" / "conversation-loop-runs"
    )
    loop_artifact_response = loop_content_app.request(
        "GET",
        f"/artifacts/{loop_artifact_id}/content",
    )
    loop_artifact = json.loads(loop_artifact_response.json()["content"])
    diff_artifact_id = loop_artifact["capability_run"]["artifact"]["artifact_id"]
    artifact_content_app = create_http_app(state_root)
    diff_artifact_response = artifact_content_app.request(
        "GET",
        f"/artifacts/{diff_artifact_id}/content",
    )

    assert diff_artifact_response.status_code == 200
    diff_artifact = json.loads(diff_artifact_response.json()["content"])
    assert diff_artifact["artifact_type"] == "native_coding.diff_result"
    assert diff_artifact["result_lines"] == ["modified src/app.py"]
    assert diff_artifact["changed_files"] == [
        {"path": "src/app.py", "status": "modified"}
    ]
    diff_artifact_text = json.dumps(diff_artifact, ensure_ascii=False)
    assert "old desktop value" not in diff_artifact_text
    assert "new desktop value" not in diff_artifact_text


def _decision(capacity_id: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {
            "kind": "call_capability",
            "capacity_id": capacity_id,
            "arguments": arguments,
            "rationale": f"Need {capacity_id} before answering.",
        }
    )


def _seed_workspace(workspace: Path) -> None:
    (workspace / "src").mkdir(parents=True)
    (workspace / "src" / "app.py").write_text(
        "def answer():\n"
        "    return 'old desktop value'\n",
        encoding="utf-8",
    )


def _seed_materialized_baseline(state_root: Path) -> None:
    baseline = state_root / "workspaces" / "desktop_code_workspace" / "src"
    baseline.mkdir(parents=True)
    (baseline / "app.py").write_text(
        "def answer():\n"
        "    return 'old desktop value'\n",
        encoding="utf-8",
    )


def _post_desktop_chat(
    server: Any,
    payload: dict[str, Any],
) -> tuple[http.client.HTTPResponse, str]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        conn = http.client.HTTPConnection(host, port, timeout=5)
        conn.request(
            "POST",
            "/desktop/chat",
            body=json.dumps(payload),
            headers={"content-type": "application/json"},
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return response, body


def _detail_content(capacity_result: dict[str, Any], label: str) -> dict[str, Any]:
    matching = [
        detail
        for detail in capacity_result["details"]
        if detail["label"] == label
    ]
    assert len(matching) == 1
    assert matching[0]["kind"] == "json"
    return matching[0]["content"]


def _parse_sse(body: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in body.strip().split("\n\n"):
        lines = block.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        events.append(
            {
                "event": event_line.removeprefix("event: "),
                "data": json.loads(data_line.removeprefix("data: ")),
            }
        )
    return events
