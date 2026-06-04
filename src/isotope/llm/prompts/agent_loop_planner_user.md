{
  "agent_id": {{ agent_id }},
  "tick_id": {{ tick_id }},
  "decision_id": {{ decision_id }},
  "control": {{ control }},
  "default_context": {{ default_context }},
  "rules": [
    "Return only a JSON object.",
    "Choose exactly one available step from control.next_actions.",
    "Use default_context.memory before selecting query_memory.",
    "Choose query_memory only when default_context.memory is insufficient.",
    "Do not execute tools or mutate state.",
    "Do not include raw prompt, raw response, messages, stdout, or artifact content."
  ],
  "required_json_shape": {
    "planner_run_id": "string",
    "agent_id": {{ agent_id }},
    "tick_id": {{ tick_id }},
    "decision_id": {{ decision_id }},
    "basis": {
      "run_id": {{ run_id }},
      "last_event_id": {{ last_event_id }}
    },
    "decision": {
      "step": "one of control.next_actions",
      "request": "object"
    },
    "rationale": "short public string"
  }
}
