{
  "workspace": {{ workspace }},
  "user_goal": {{ user_goal }},
  "planning_trigger": {{ planning_trigger }},
  "facts": {{ facts }},
  "parallel_launch_limit": {{ parallel_launch_limit }},
  "write_mode": {{ write_mode }},
  "accepted_output_formats": [
    "首选严格 JSON。",
    "如果模型无法稳定输出 JSON，可输出清晰 TOML；系统会先用本地解析器转成 JSON。",
    "无论哪种格式，都必须包含可执行 goals。"
  ],
  "output_schema": {
    "plan_summary": "面向完整功能板块的可审阅计划摘要；如果只是在拆一个小目标，可用一句话说明范围。",
    "phases": [
      {
        "name": "阶段或批次名称",
        "goals": ["本阶段覆盖的可执行目标或交付点"],
        "stop_conditions": ["本阶段应该暂停或回到用户的条件"],
        "acceptance_conditions": ["本阶段可验收的具体证据"]
      }
    ],
    "parallel_recommendations": [
      {
        "batch": "可并行批次名称",
        "targets": ["可并行 worker target_name"],
        "reason": "为什么这些目标可以并行"
      }
    ],
    "stop_conditions": ["整个板块规划应停止或请求用户的条件"],
    "acceptance_conditions": ["整个板块完成验收所需的证据"],
    "goals": [
      {
        "goal": "清晰、可执行、可交给 Codex worker 的目标",
        "target_name": "短横线命名的 worker 名",
        "reason": "一句话说明依据来自哪些当前事实",
        "depends_on": ["可选，必须先完成并合入的 target_name 或 goal_id"],
        "stage": "可选，同阶段可并行；后续阶段必须等前置阶段完成",
        "scope": "可选，本目标触碰的代码或文档范围",
        "merge_gate": "可选，解锁本目标前必须完成的 merge gate 名称"
      }
    ]
  },
  "rules": [
    "每个 goal 必须能独立启动一个 Supervisor worker。",
    "完整规划可以多于 parallel_launch_limit；parallel_launch_limit 只表示建议首批并发上限，不是规划截断上限。",
    "如果 user_goal 存在，必须围绕它拆解可执行目标。",
    "如果 facts 包含 conversation.research_context，必须把它当作已完成调研事实来使用；plan_summary、reason 和每个 worker-facing goal 要体现这些调研发现，不要把已完成的调研重新规划成搜索或资料搜集任务。",
    "当 user_goal 指向完整功能板块时，必须输出 plan_summary、phases、parallel_recommendations、stop_conditions 和 acceptance_conditions。",
    "不要输出泛泛的继续推进、优化系统、阅读文档。",
    "不要生成需要用户另行解释范围的任务。",
    "target_name 使用小写字母、数字和短横线。"
  ]
}
