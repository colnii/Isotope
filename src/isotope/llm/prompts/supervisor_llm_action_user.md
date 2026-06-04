{
  "allowed_kinds": {{ allowed_kinds }},
  "available_workspaces": {{ available_workspaces }},
  "candidate_targets": {{ candidate_targets }},
  "active_goals": {{ active_goals }},
  "resumable_session_ids": {{ resumable_session_ids }},
  "completed_session_ids": {{ completed_session_ids }},
  "command_suggestions": {{ command_suggestions }},
  "recent_context_results": {{ recent_context_results }},
  "recent_decision_answers": {{ recent_decision_answers }},
  "context_request_history": {{ context_request_history }},
  "planner_priority": {{ planner_priority }},
  "blocked_context_priority": {{ blocked_context_priority }},
  "capacity_decisions": {{ capacity_decisions }},
  "worker_profiles": {
    "coding": "默认代码开发档，适合需要改代码、跑测试、做复杂判断的任务。",
    "light": "低成本轻任务档，适合轻量检查、状态汇报、smoke 或短小验证。"
  },
  "delete_worktree_candidates": {{ delete_worktree_candidates }},
  "worker_lifecycle_contract": {{ worker_lifecycle_contract }},
  "action_rules": [
    "执行路径：recommendation.target_session_id 是状态线索；可执行目标来自 command_suggestions、resumable_session_ids 或 active_goals。",
    "resume_session.session_id 来自 resumable_session_ids；列表为空时选择 request_context、launch_session、ask_user 或 monitor。",
    "completed_session_ids 里的会话已经完成或归档；需要继续下一批时使用 request_context 或 launch_session。",
    "context_request_history 记录已查过的 cwd/query 组合；已有结果时换新 query 或选择推进动作。",
    "已有上下文足够时优先选择 launch_session、send_continue、send_status、ask_user 或 monitor。",
    "active_goals 里的目标仍然活跃；last_status 为 blocked/needs_user 时根据已有信息选择 request_context、launch_session、ask_user 或 monitor。",
    "active_goals 里同名 worker 已在运行时，根据 worker_status 选择 monitor、send_status、send_continue、ask_user 或等待下一轮。",
    "已有 active goal worker 正在运行时优先 monitor 或等待下一轮；后续 request_context 或 launch_session 需要新的目标证据。",
    "已有 merge dispatch worker 正在运行时优先 monitor 或等待下一轮；后续 request_context 或 launch_session 需要新的目标证据。",
    "launch_session 如果命中已有 command_suggestions 的 target_name，可以输出 target_name 和 reason；Supervisor 会从白名单命令补 cwd 和 prompt，长 goal 文本留在命令建议里。",
    "blocked/needs_user 目标满足 decision_gate 时使用 ask_user；其余情况继续查上下文或启动新 worker 推进。",
    "blocked/needs_user 目标缺少上下文时优先 request_context；仍无法判断且满足 decision_gate 后输出 ask_user。",
    "recent_decision_answers 是用户已经拍板的答案；相关 goal 或 session 后续按答案继续推进。",
    "candidate_targets.resume_context_hint 为 large_session_file 时，恢复历史可能消耗大量 tokens；除非确实需要该完整历史，恢复前优先考虑 request_context 或 launch_session。",
    "worker_reviews 提供下一轮决策上下文；next_decision.merge_suitable 进入复查合并路径，merge/rebase/delete 走白名单动作和对应候选。",
    "worker_lifecycle_contract.decision 是程序托管的 worker 生命周期状态；execution 已记录的动作视为完成记录，后续选择剩余步骤。",
    "worker_lifecycle_contract.execution.summary 是程序汇总的生命周期队列：archivable/delete_ready/delete_blocked/result_actions；先读它再判断是否需要补上下文、等待或选择白名单动作。",
    "worker_lifecycle_contract.execution.recommended_next_step 是程序派生的固定流程建议；优先按它判断 monitor、archive_ready、delete_ready、delete_blocked 或 merge_dispatch_ready。",
    "worker_lifecycle_contract.decision.next_step 是程序判断的下一步；launch_merge_worker 走现有 merge dispatch，archive_worker/cleanup_worktree 只有存在匹配白名单候选时才可输出动作，否则 monitor。",
    "delete_worktree 是受控清理动作；用于 delete_worktree_candidates 中已经完成、已归档、已集成的 worker；输出前设置 confirm_delete_worktree=true。",
    "capacity_decisions 来自 capacity plan 的 supervisor_decision 读模型；next_action 为 call_capacity 时说明能力计划已 ready，request_input 表示需要先补输入，blocked 表示当前能力不可启动。",
    "capacity_decisions 中同一 capacity_id 的 next_action=call_capacity 且 can_execute_agent_loop=true 时，输出 call_capacity。"
  ],
  "context_capability": {
    "kind": "request_context",
    "description": "信息不足时，按 query 主动检索项目上下文；结果会返回 ranked evidence（排序证据）的 title/path/snippet/score/match_reason；按需检索，避免每轮固定塞文档全文。",
    "schema": {
      "kind": "request_context",
      "cwd": "/path/to/repo",
      "query": "要查的问题或关键词",
      "reason": "一句中文原因"
    }
  },
  "decision_gate": {
    "kind": "ask_user",
    "description": "同时满足三项时使用 ask_user 让用户拍板：Codex 已明确提出拍板请求；LLM 无法从用户已有指示判断；已检索上下文且结果缺失、过时或冲突。",
    "schema": {
      "kind": "ask_user",
      "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
      "goal_id": "goal-optional-for-goal-level-request",
      "question": "需要用户拍板的问题",
      "codex_requested_decision": true,
      "instructions_exhausted": true,
      "context_status": "missing|outdated|conflict",
      "reason": "一句中文原因"
    }
  },
  "generated_at": {{ generated_at }},
  "recommendation": {{ recommendation }},
  "worker_reviews": {{ worker_reviews }},
  "output_schema": {
    "kind": "resume_session",
    "target_name": "lane-a",
    "session_id": "019e35a2-e442-75e2-84ab-3761a685a736",
    "prompt_kind": "send_continue",
    "reason": "一句中文原因"
  },
  "launch_schema": {
    "kind": "launch_session",
    "target_name": "new-lane",
    "cwd": "/path/to/repo，可省略：命中已有 target_name 时由白名单命令补齐",
    "prompt": "可省略：命中已有 target_name 时由白名单命令补齐；否则写给新 Codex 会话的中文指令",
    "worker_profile": "coding|light",
    "reason": "一句中文原因"
  },
  "delete_worktree_schema": {
    "kind": "delete_worktree",
    "target_name": "done-lane",
    "record_id": "managed-optional-but-recommended",
    "confirm_delete_worktree": true,
    "reason": "一句中文说明已确认完成、归档且集成"
  },
  "call_capacity_schema": {
    "kind": "call_capacity",
    "capacity_id": "capacity_decisions 中 ready 的 capacity_id",
    "reason": "一句中文说明为什么现在调用该能力"
  }
}
