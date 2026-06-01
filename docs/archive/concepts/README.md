# Isotope 概念文档

状态：`concept index`

这个目录保存从早期 `Isotope` 讨论中迁入的长期概念文档和应用层设计文档。

这些文档不是当前内核实现状态的事实来源。当前实现状态仍以这些文件为准：

1. [Current Status](../../current/status.md)
2. [Agent Task Queue](../../current/agent-task-queue.md)
3. [Kernel Living Spec](../../archive/architecture/kernel-v0.1/kernel-living-spec.md)

## 来源映射

下面这些文件来自 `/home/lumber/Github/x-agent/docs/superpowers/specs/`，迁入时保持原文件名不变。

| 原文件 | Isotope 中的位置 |
| --- | --- |
| `2026-04-21-isotope-platform-kernel-reference-design.md` | [2026-04-21-isotope-platform-kernel-reference-design.md](2026-04-21-isotope-platform-kernel-reference-design.md) |
| `2026-04-22-isotope-vs-langgraph-vs-autogen.md` | [2026-04-22-isotope-vs-langgraph-vs-autogen.md](2026-04-22-isotope-vs-langgraph-vs-autogen.md) |
| `2026-04-22-isotope-vs-codex-claude-code-openclaw.md` | [2026-04-22-isotope-vs-codex-claude-code-openclaw.md](2026-04-22-isotope-vs-codex-claude-code-openclaw.md) |
| `2026-04-24-isotope-vs-genericagent.md` | [2026-04-24-isotope-vs-genericagent.md](2026-04-24-isotope-vs-genericagent.md) |
| `2026-04-24-isotope-vs-petgpt.md` | [2026-04-24-isotope-vs-petgpt.md](2026-04-24-isotope-vs-petgpt.md) |
| `2026-04-22-isotope-study-agent-boundaries.md` | [2026-04-22-isotope-study-agent-boundaries.md](2026-04-22-isotope-study-agent-boundaries.md) |
| `2026-04-22-isotope-marxist-leninist-study-agent-design.md` | [2026-04-22-isotope-marxist-leninist-study-agent-design.md](2026-04-22-isotope-marxist-leninist-study-agent-design.md) |
| `2026-04-22-isotope-first-study-companion-spec.md` | [2026-04-22-isotope-first-study-companion-spec.md](2026-04-22-isotope-first-study-companion-spec.md) |
| `2026-04-22-isotope-persona-architecture.md` | [2026-04-22-isotope-persona-architecture.md](2026-04-22-isotope-persona-architecture.md) |
| `2026-04-22-study-companion-to-isotope-kernel-requirements.md` | [2026-04-22-study-companion-to-isotope-kernel-requirements.md](2026-04-22-study-companion-to-isotope-kernel-requirements.md) |
| `2026-04-23-isotope-study-companion-kernel-tension-notes.md` | [2026-04-23-isotope-study-companion-kernel-tension-notes.md](2026-04-23-isotope-study-companion-kernel-tension-notes.md) |

## 额外概念文档

- [Isotope vs Hermes Agent](isotope-vs-hermes-agent.md)
- [ChatGPT Share Feedback Notes](2026-05-11-isotope-chatgpt-share-feedback-notes.md)

## 阅读规则

这些文档用于给未来产品和应用层工作施加概念压力。

不要把它们当成当前实现队列。它们不能直接授权我们现在加入 domain pack、真实 LLM loop、搜索 provider、persona system、memory query engine 或真实 workspace substrate。只有当前 kernel queue 明确打开对应 track 时，才应该进入实现。
