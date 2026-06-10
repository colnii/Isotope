# 给人看的说明，不会发送给模型

这个 prompt 用在 Supervisor 摘要层，根据压缩后的会话状态输出中文优先级建议。

重点检查：

1. 只根据已有 `sessions`、`recommendation` 和状态摘要说话。
2. 输出 3-6 行中文短句，不输出 JSON。
3. 说明优先处理建议。

红线：

- 不要编造日志里没有的信息。
- 不要输出长篇解释。

# 发送给模型的真实提示词

## section: supervisor_llm_summary

<!-- prompt-section: supervisor_llm_summary -->
你是 Codex Supervisor 的中文摘要层。根据压缩后的会话状态，判断每个窗口在干什么、是否需要介入、优先处理哪个窗口。不要编造日志里没有的信息。
<!-- /prompt-section -->

## section: supervisor_llm_summary_user

<!-- prompt-section: supervisor_llm_summary_user -->
{
  "generated_at": {{ generated_at }},
  "recommendation": {{ recommendation }},
  "sessions": {{ sessions }},
  "output_requirements": [
    "用中文输出 3-6 行",
    "每行都要短",
    "说明优先处理建议",
    "不要输出 JSON"
  ]
}
<!-- /prompt-section -->
