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
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id supervisor_project_status_fixture --json"
    )


def test_changed_surface_recommends_self_repair_case_for_self_repair_diff():
    diff_text = """
diff --git a/src/isotope/features/supervisor/self_repair.py b/src/isotope/features/supervisor/self_repair.py
+ SELF_REPAIR_WORKER_ROLE = "self_repair"
+ isotope.self_repair
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is True
    assert "self_repair_contract_changed" in result.reason_codes
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id isotope_self_repair_fixture --json"
    )


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


def test_changed_surface_ignores_unchanged_diff_context_lines():
    diff_text = """
diff --git a/docs/current/supervisor-dev-evals.md b/docs/current/supervisor-dev-evals.md
@@ -1,5 +1,5 @@
 capability contracts, capacity_observation, and LLM prompts are mentioned here.
-Old wording.
+New wording.
"""

    result = detect_changed_surface(diff_text)

    assert result.eval_required is False
    assert result.reason_codes == []


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


def test_changed_surface_does_not_self_match_dev_eval_fixture_strings():
    diff_text = """
diff --git a/src/isotope/dev_evals/changed_surface.py b/src/isotope/dev_evals/changed_surface.py
+ "src/isotope/features/supervisor/self_repair.py"
+ "self_repair_contract_changed"
+ "supervisor_conversation_loop"
diff --git a/tests/unit/dev_evals/test_changed_surface.py b/tests/unit/dev_evals/test_changed_surface.py
+ "supervisor.integration_review"
"""

    result = detect_changed_surface(diff_text)

    assert result.reason_codes == ["dev_eval_contract_changed"]
    assert result.recommended_command == (
        "scripts/dev-eval supervisor_capacity_eval "
        "--suite supervisor_capacity_basic --case-id code_search_fixture --json"
    )
