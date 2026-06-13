# Research Recall Product Preview Design

## Goal

Make `research.recall` visible as a readable product result in Supervisor capacity
outputs and the desktop capacity card details.

## Scope

This slice consumes the existing `research.recall` capability result. It does
not change capability selection, planner prompts, artifact inspect behavior,
memory promotion, or report full-content expansion.

## Current Problem

`research.recall` can retrieve `research.report` artifact previews, but the
capacity result projection and desktop card helpers only have special handling
for `research.search`. If an agent loop calls `research.recall`, the desktop UI
falls back to generic JSON and the compact card does not communicate that report
previews were recalled.

## Design

Add a low-sensitive projection for `research.recall` in
`capacity_result.py`. The projection should expose:

- `agent_loop_research_recall_status`;
- `agent_loop_research_recall_result_count`;
- `agent_loop_research_recall_content_policy`;
- `agent_loop_research_recall_retrieval_backend`;
- `agent_loop_research_recall_dense_status`;
- `agent_loop_research_recall_previews`.

Each preview contains only `run_id`, `artifact_id`, `artifact_type`, `summary`,
`ref`, `source_refs`, and `provenance`. It must not include report `content`.

On desktop, extend the existing `capacityCallView.ts` helper layer:

- summarize `research.recall` cards in product language;
- extract preview records from `agent_loop_research_recall_previews`;
- keep filtering out invalid records before Svelte rendering.

`CapacityCallDetails.svelte` should render these previews as a compact list, then
keep the raw JSON in the existing collapsed `结果原文` disclosure. This matches
the existing source-preview pattern for `research.search`.

## Error Handling

If `results` or `retrieval` are missing or malformed, the projection still
returns status and a zero count. The UI falls back to generic JSON rendering when
there are no valid previews.

## Testing

Add failing tests first for:

- capacity projection of `research.recall` fields without content leakage;
- desktop summary text for `research.recall`;
- desktop preview extraction from details;
- Svelte detail component using the new helper and keeping raw JSON disclosure.

Run targeted Python and desktop unit tests plus the Supervisor dev-eval gate when
`changed_surface` requires it.
