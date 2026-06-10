# Supervisor Capacity Dev Eval Design

Date: 2026-06-11

## Goal

Build a developer-only eval gate for Supervisor capacity and LLM-agent changes.
Codex should be able to run it during development without the user asking every
time, understand whether the behavior is still healthy, and continue fixing when
the eval shows that the agent path is not working.

## Problem

Current tests cover many deterministic contracts, but they do not answer the
developer question: when a real LLM is allowed to choose capabilities, does it
actually call the right capability for a realistic task, and does that
capability still complete successfully?

The gate must not become a public product entrypoint. It is a development aid
for Codex and maintainers. It also must not depend on a brittle directory list:
Isotope's module layout changes often, so path-only trigger rules would silently
miss regressions after refactors.

## Success Criteria

- Codex has one low-context preflight command that tells it whether the live eval
  is required for the current diff.
- If the preflight says the eval is required, token cost is not an acceptable
  reason to skip it.
- If live LLM or network configuration is missing, the run degrades explicitly to
  deterministic regression checks and reports the blocked reason.
- Eval reports include hard gates, per-step capability traces, reviewer scores,
  failure gates, regression risks, and a recommended next fix.
- Every currently registered capability has a reasonable eval scenario, unless
  it only makes sense as part of a necessary multi-capability combination.
- Eval cases must exercise real LLM capability selection; deterministic checks
  can validate harness behavior but cannot replace live LLM evals when the gate
  requires them.
- The eval reuses existing capacity and desktop conversation contracts instead
  of inventing a parallel agent loop.
- Public docs and user-facing command tables do not advertise this as a product
  feature.

## Non-Goals

- Do not add a new public `pyproject.toml` script.
- Do not make ordinary users run this from the desktop UI.
- Do not replace existing unit, integration, or smoke tests.
- Do not use LLM judging as the only pass/fail signal. Hard gates stay
  deterministic.
- Do not store raw prompts, raw responses, API keys, full transcripts, or full
  artifact content in public reports.

## Developer Flow

Codex runs this before claiming a relevant development task is complete:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.changed_surface --base origin/main --json
```

The command returns a compact payload:

```json
{
  "eval_required": true,
  "suite": "supervisor_capacity_basic",
  "reason_codes": ["capability_contract_changed", "llm_prompt_changed"],
  "recommended_command": "PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.supervisor_capacity_eval --suite supervisor_capacity_basic --json"
}
```

If `eval_required` is true, Codex must run the recommended command unless the
environment is missing required provider configuration. In that blocked case it
must still run deterministic regression checks and report the exact blocker.

The live eval command is intentionally a Python module path, not an installed
public script:

```bash
PYTHONPATH=src .venv/bin/python -m isotope.dev_evals.supervisor_capacity_eval --suite supervisor_capacity_basic --json
```

Pytest can call the same implementation from an opt-in file:

```bash
ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1 .venv/bin/python -m pytest tests/evals/test_supervisor_capacity_live_eval.py -q
```

## Stable Trigger Design

`changed_surface` should prefer semantic surface detection over directory
matching. It reads the git diff and emits short reason codes. Directory paths can
be a fallback, but they are not the source of truth.

Primary semantic signals:

- Capability metadata changed: `capability_id`, `input_contract`,
  `output_contract`, `Capability`, `CapabilityCatalog`, or `run_capability`.
- Conversation contract changed: `capacity_manifest`, `capacity_observation`,
  `call_capability`, `call_capabilities`, `direct_answer`, or
  `report_capability_gap`.
- Prompt registry changed: `SYSTEM_PROMPT_NAMES`, `USER_PROMPT_TEMPLATE_NAMES`,
  `supervisor_conversation_loop`, `capacity_calling`, or prompt markdown assets.
- Agent-loop result projection changed: `model_observation`,
  `agent_loop_json_result`, capacity result details, SSE `capacity_start` /
  `capacity_result`, or low-sensitive output filtering.
- Research, memory, native coding, or goal planning capability contracts changed.
- Public command or test contract changed: CLI parser for capacity/research/LLM
  paths, golden event names, or capability result schema assertions.

Fallback path hints may include current known locations such as
`src/isotope/capabilities`, `src/isotope/llm`, and
`src/isotope/features/supervisor`, but a file move must not disable the gate if
the semantic diff still touches the above surface.

The output should stay small so other Codex development directions only need to
remember one rule: run `changed_surface`; if it says required, run the
recommended eval.

## Eval Suites

The first suite is `supervisor_capacity_basic`.

The suite starts from a capability scenario catalog. Each registered capability
gets one minimal realistic user task, expected capability ids, fixture setup,
and deterministic hard gates. If a capability has no reasonable standalone user
task, it is covered by the smallest necessary combination scenario.

Examples:

- `code.search`: user asks where a known symbol or phrase appears in the fixture
  repo. Hard gate: LLM calls `code.search`, the result status is ok, and the
  matched path is present.
- `code.read`: user asks to inspect a known file. Hard gate: LLM calls
  `code.read`, the result status is ok, and the excerpt contains the expected
  marker.
- `vcs.status`: user asks what changed in the working tree. Hard gate: LLM calls
  `vcs.status`, the result status is ok, and the known changed file appears.
- `research.search`: user asks for a focused external research check. Hard gate:
  LLM calls `research.search`, the call completes or reports a provider failure
  explicitly, and the report records the provider status.
- `supervisor.goal_plan`: user asks to turn a concrete goal into Supervisor
  goals. Hard gate: LLM calls `supervisor.goal_plan` and the goal-plan payload is
  present.
- `artifact.diff_result`: covered by a combination scenario that first creates
  or materializes a workspace with a known diff, because the artifact capability
  is not useful without prior workspace state.
- `coding_task.apply_reviewed_diff`: covered by a combination scenario with
  prepared workspace id and expected source digests, because direct standalone
  invocation would not represent a real workflow.

The first implementation should build the catalog for every currently registered
capability. A scenario can be marked as combination-only or configuration-gated,
but it should not be missing from the catalog. It should not start from the
earlier complex research-and-planning example.

## Required LLM Behavior

Every capability scenario must call a real configured LLM provider to choose the
capability. A deterministic provider may be used only for harness unit tests,
schema tests, and failure injection.

The harness should capture the model-visible task, the chosen capability ids,
the public capacity trace, and the sanitized result. Mechanical gates decide
whether each call succeeded:

- expected capability id was called;
- required input summary is present and low-sensitive;
- capacity result status is ok, or the allowed provider-failure status is
  explicitly recorded for externally configured services;
- no raw prompt, raw response, secret, transcript, or full artifact content
  leaked into the public report;
- final answer is grounded in the relevant capacity observation when the case
  expects an answer.

## Reviewer Prompt Loop

After a suite run, the harness should emit a reviewer prompt for Codex. This is
not a fully separate autonomous reviewer agent in v1. It is a prompt artifact
that asks the current Codex session to review the current diff, the trace, the
scores, and the failure gates before making more changes.

The prompt should instruct Codex to:

- inspect the current git diff;
- read the eval trace and failure gates;
- score its own work against the scenario catalog;
- identify whether a failure is a product-direction problem, capability-contract
  problem, prompt problem, or implementation bug;
- when the task asks for maturity/latest-practice judgment, perform fresh
  research first instead of relying on memory;
- compare the current behavior with mature AI product and agent practice only as
  far as the trace and diff justify;
- make the smallest necessary correction;
- rerun the required eval or deterministic fallback;
- report what changed, which gate now passes, which gate still fails, and the
  remaining risk.

The reviewer prompt is allowed to be opinionated, but it must be tied to
evidence: diff paths, capacity ids, trace steps, hard-gate failures, and command
outputs.

## Report Contract

The eval returns one JSON object:

```json
{
  "kind": "supervisor_capacity_dev_eval_report",
  "suite": "supervisor_capacity_basic",
  "status": "passed",
  "hard_gate_passed": true,
  "cases": [
    {
      "case_id": "code_search_symbol",
      "capability_under_test": "code.search",
      "status": "passed",
      "hard_gates": [
        {
          "gate": "required_capacity_called",
          "passed": true,
          "details": {"capacity_ids": ["code.search"]}
        }
      ],
      "steps": [
        {
          "capacity_id": "code.search",
          "status": "ok",
          "input_summary": {"query": "known_fixture_symbol"}
        }
      ],
      "scores": {
        "capacity_choice": 4,
        "input_quality": 4,
        "result_grounding": 4,
        "self_review_quality": 3
      },
      "regression_risks": [],
      "reviewer_prompt_ref": {
        "path": "state/dev-evals/reviewer-prompts/code_search_symbol.md"
      },
      "recommendation": "No immediate fix required."
    }
  ]
}
```

Hard gates are deterministic and decide pass/fail. Rubric scores explain
quality. The reviewer prompt can ask Codex to self-score from the trace and
diff, but that self-score cannot override a failed hard gate.

## Architecture

Add a small `isotope.dev_evals` package with focused modules:

- `changed_surface`: reads git diff, detects semantic surface reason codes, and
  prints compact JSON.
- `supervisor_capacity_eval`: orchestrates deterministic and live eval cases.
- `cases`: stores the capability scenario catalog, fixture setup, expected
  capability ids, and required hard gates.
- `gates`: deterministic assertions over event traces and capability results.
- `rubric`: rule-based scoring plus optional Codex reviewer self-scoring fields.
- `reviewer_prompt`: renders the prompt artifact that asks Codex to inspect the
  diff, trace, scores, failure gates, and maturity/latest-practice gaps before
  modifying code again.
- `reporting`: serializes the low-sensitive JSON report.

The eval should call `run_supervisor_conversation_events(...)` directly for the
main harness. That exercises the same capacity manifest,
capacity_start/capacity_result events, observation projection, and direct-answer
guard used by the product path without adding HTTP server overhead. A narrow
desktop-chat server smoke can remain a later regression layer if the streaming
transport itself changes.

## Error Handling

- Missing LLM provider: report `status="blocked"` with
  `reason_code="llm_provider_missing"` and run deterministic regression cases.
- Missing research provider or network: report the provider failure as a case
  result; do not hide it as a pass.
- Capability execution error: fail the hard gate for that case and include the
  public error summary.
- Invalid model JSON: fail the case and include the parse failure category.
- Prompt or transcript leakage in report: fail the report sanitizer test.
- Reviewer prompt generation failure: fail the report only if hard gates failed
  and there is no actionable next instruction for Codex; otherwise mark the
  reviewer prompt as unavailable with a reason code.

## Testing

Implementation should be test-first.

Deterministic tests:

- `changed_surface` returns `eval_required=true` for semantic diffs touching
  capability contracts, prompt registry, capacity observations, and result
  projection symbols.
- `changed_surface` does not require eval for unrelated docs-only diffs.
- Every scenario in the initial catalog maps to at least one registered
  capability id or an explicit combination scenario.
- Hard gates fail when a model does not call the expected capability id.
- Hard gates fail when a capability result status is not ok and the case did not
  allow that provider failure.
- Report serialization omits raw prompts, raw responses, API keys, and full
  transcripts.
- Reviewer prompt includes diff/trace/gate/score sections and instructs Codex to
  modify, rerun, and report.

Opt-in live tests:

- Run the `supervisor_capacity_basic` suite only when
  `ISOTOPE_RUN_LIVE_SUPERVISOR_EVAL=1`.
- If provider configuration is missing, the test records a blocked result
  instead of pretending success.
- When configured, the live suite must call a real LLM provider for each selected
  scenario, pass hard gates, and print the report path or JSON summary for
  developer review.

## Documentation

Add a short developer-facing note at `docs/current/supervisor-dev-evals.md`.
The note should say:

- Run `changed_surface` before finishing Supervisor capacity or LLM-agent work.
- If it says eval is required, run the recommended command.
- Token cost is not a valid skip reason for required live evals.
- Provider/network absence is the only acceptable live-eval blocker, and it must
  be reported with deterministic regression results.
- After running a required suite, feed the generated reviewer prompt back into
  Codex before claiming the development task is complete.

Do not add this to public quick-start tables as an end-user feature.
