{
  "task": "repair_goal_planning_output",
  "raw_answer": {{ raw_answer }},
  "original_goal_request": {{ original_goal_request }},
  "required_json_shape": {
    "plan_summary": "可选，规划摘要",
    "phases": [
      {
        "name": "可选，阶段名",
        "goals": ["可选，本阶段目标"],
        "stop_conditions": ["可选，暂停条件"],
        "acceptance_conditions": ["可选，验收条件"]
      }
    ],
    "parallel_recommendations": [
      {
        "batch": "可选，并行批次名",
        "targets": ["可选，worker target_name"],
        "reason": "可选，并行原因"
      }
    ],
    "stop_conditions": ["可选，整体暂停条件"],
    "acceptance_conditions": ["可选，整体验收条件"],
    "goals": [
      {
        "goal": "必填，可执行目标",
        "target_name": "必填，小写短横线 worker 名",
        "reason": "必填，依据",
        "depends_on": ["可选，依赖的 target_name 或 goal_id"],
        "stage": "可选，阶段名",
        "scope": "可选，影响范围",
        "merge_gate": "可选，依赖的 merge gate"
      }
    ]
  },
  "rules": [
    "必须输出一个 JSON object。",
    "必须包含非空 goals 数组。",
    "不得输出 Markdown 代码块包裹。",
    "如果原文没有 target_name，按 goal 生成短横线英文名。"
  ]
}
