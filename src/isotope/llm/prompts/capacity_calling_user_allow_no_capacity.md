{
  "goal": {{ goal }},
  "capacities": {{ capacities }},
  "rules": [
    "Select one offered capacity_id only when the goal needs a capacity call.",
    "If the goal can be answered without a capacity call, set capacity_id to null and arguments to {}.",
    "Fill only arguments needed by that capacity input_contract.",
    "If a required value is absent from the goal, omit that argument.",
    "Return only a JSON object and do not execute anything."
  ],
  "required_json_shape": {
    "capacity_id": "string or null",
    "arguments": "object",
    "confidence": "number between 0 and 1",
    "rationale": "short low-sensitive string"
  }
}
