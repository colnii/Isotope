from __future__ import annotations
from typing import Any
from ._cap_common import builtin_capability


def screen_capability_definitions(capability_type: type[Any]) -> list[Any]:
    return [
        capability_type(
        capability_id="screen.observe",
        title="Screen Observe",
        description=(
        "Run a policy-gated local screen observation and return "
        "the shared screen report."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=(
        "screen",
        "observe",
        "screenshot",
        "metadata",
        "gui",
        ),
        input_contract={
        "type": "object",
        "required": ["target_selector"],
        "properties": {
        "target_selector": {
        "type": "object",
        "description": (
        "Window selector with kind=window and selector "
        "keys such as app, title_contains, or window_id."
        ),
        },
        "target_allowlist": {
        "type": "object",
        "description": (
        "Optional allowed_apps / allowed_title_contains "
        "policy override for this observe call."
        ),
        },
        "capture": {
        "type": "array",
        "description": (
        "Capture kinds, limited to metadata and screenshot."
        ),
        },
        "mode": {
        "type": "string",
        "enum": ["non_intrusive"],
        "description": "Observation mode.",
        },
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": (
        "Optional runtime root. Agent loop calls use "
        "their capability root when this is omitted."
        ),
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "screen_observe",
        "screen_report",
        ],
        },
        safety_boundaries=(
        "policy_gated_screen_observe",
        "local_backend_only",
        "screen_report_artifact",
        "no_screenshot_content_in_events",
        "screenshot_content_for_model_observation",
        "no_input_execution",
        "target_allowlist_supported",
        ),
        default_enabled=True,
        network_required=False,
        ),
        capability_type(
        capability_id="screen.report",
        title="Screen Report",
        description=(
        "Summarize existing screen run records through the shared "
        "public observe/control plan report boundary."
        ),
        maturity="v0.2",
        shelf="product_candidate",
        domain_tags=(
        "screen",
        "report",
        "observe",
        "control-plan",
        "gui",
        ),
        input_contract={
        "type": "object",
        "required": ["root", "run_id"],
        "properties": {
        "root": {
        "type": "string",
        "x-system-input": True,
        "description": "Runtime root containing runs/*/artifacts.",
        },
        "run_id": {
        "type": "string",
        "description": "Run id whose screen artifacts should be summarized.",
        },
        },
        },
        output_contract={
        "type": "object",
        "fields": [
        "status",
        "run_id",
        "summary",
        "artifacts",
        ],
        },
        safety_boundaries=(
        "screen_artifact_projection",
        "public_result_metadata",
        "no_screenshot_content",
        "no_input_execution",
        "no_window_mutation",
        ),
        default_enabled=True,
        network_required=False,
        ),
    ]
