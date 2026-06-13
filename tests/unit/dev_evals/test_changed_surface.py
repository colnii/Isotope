from isotope.dev_evals.changed_surface import detect_changed_surface


def test_changed_surface_requires_eval_for_capability_contract_diff():
    diff_text = """
diff --git a/src/isotope/capabilities/catalog.py b/src/isotope/capabilities/catalog.py
+ capability_id="code.search"
+ input_contract={"type": "object"}
+ output_contract={"type": "object"}
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert result.suite == "supervisor_capacity_basic"
    assert "capability_contract_changed" in result.reason_codes
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id code_search_fixture --json"
    )
    assert result.full_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --json"
    )


def test_changed_surface_recommends_screen_control_approval_case_for_screen_control_diff():
    diff_text = """
diff --git a/src/isotope/llm/tool_bridge.py b/src/isotope/llm/tool_bridge.py
+    if tool_name == "screen_control":
+        return _submit_screen_control_tool_call(app, run_id, arguments)
diff --git a/src/isotope/capabilities/catalog.py b/src/isotope/capabilities/catalog.py
+                    capability_id="screen.control",
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id screen_control_approval_fixture "
        "--deterministic-provider --json"
    )
    assert result.full_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --json"
    )


def test_changed_surface_requires_eval_for_prompt_and_observation_diff():
    diff_text = """
diff --git a/src/isotope/llm/prompts/supervisor_conversation_loop.md b/src/isotope/llm/prompts/supervisor_conversation_loop.md
+ capacity_observation
+ call_capability
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert result.reason_codes == [
        "conversation_contract_changed",
        "llm_prompt_changed",
    ]


def test_changed_surface_does_not_require_eval_for_unrelated_docs_diff():
    diff_text = """
diff --git a/docs/current/README.md b/docs/current/README.md
+ typo fix in onboarding prose
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is False
    assert result.reason_codes == []
    assert result.recommended_command is None
    assert result.full_command is None


def test_changed_surface_requires_eval_for_dev_eval_contract_diff():
    diff_text = """
diff --git a/src/isotope/dev_evals/supervisor_capacity_eval.py b/src/isotope/dev_evals/supervisor_capacity_eval.py
+ report["run_root"] = str(root)
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert "dev_eval_contract_changed" in result.reason_codes
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id code_search_fixture --json"
    )
    assert result.full_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --json"
    )
