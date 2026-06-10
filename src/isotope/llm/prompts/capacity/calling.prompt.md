# 给人看的说明，不会发送给模型

这个 prompt 只做一件事：根据用户目标和可用能力清单，判断要不要调用一个
Isotope capacity，并填写它的参数。

重点检查：

1. 模型只能从本轮 `capacities` 里选择 `capacity_id`。
2. `capacities` 只是能力清单，不是执行结果。
3. 参数只能来自用户目标和 `input_contract`，不能编造。
4. `allow_no_capacity` 只是“是否允许不调用能力”的策略差异，不是新场景。

红线：

- 这个 prompt 只输出选择结果，不负责执行 capacity。
- 用户目标里没有的 required 参数先省略，交给后续校验或澄清。
- strict 版本必须选择 capacity；optional 版本可以把 `capacity_id` 设为 null。

# 发送给模型的真实提示词

## section: capacity_calling

<!-- prompt-section: capacity_calling -->
你决定 Isotope 是否需要调用一个 capacity，并填写该 capacity 的参数。只输出一个公开 JSON object，不要执行任何动作。
<!-- /prompt-section -->

## section: capacity_calling_user

<!-- prompt-section: capacity_calling_user -->
{
  "goal": {{ goal }},
  "capacities": {{ capacities }},
  "rules": [
    "必须选择一个 capacity_id；capacity_id 只能来自 offered capacities，且只在 goal 确实需要 capacity call 时选择。",
    "只填写该 capacity input_contract 需要的 arguments。",
    "如果 required value 不在 goal 里，先省略该 argument。",
    "只返回 JSON object，不要执行任何动作。"
  ],
  "required_json_shape": {
    "capacity_id": "string",
    "arguments": "object",
    "confidence": "number between 0 and 1",
    "rationale": "short public string"
  }
}
<!-- /prompt-section -->

## section: capacity_calling_user_allow_no_capacity

<!-- prompt-section: capacity_calling_user_allow_no_capacity -->
{
  "goal": {{ goal }},
  "capacities": {{ capacities }},
  "rules": [
    "只在 goal 确实需要 capacity call 时选择一个 capacity_id；capacity_id 只能来自 offered capacities。",
    "如果 goal 可以不调用 capacity 直接回答，把 capacity_id 设为 null，arguments 设为 {}。",
    "只填写该 capacity input_contract 需要的 arguments。",
    "如果 required value 不在 goal 里，先省略该 argument。",
    "只返回 JSON object，不要执行任何动作。"
  ],
  "required_json_shape": {
    "capacity_id": "string or null",
    "arguments": "object",
    "confidence": "number between 0 and 1",
    "rationale": "short public string"
  }
}
<!-- /prompt-section -->
