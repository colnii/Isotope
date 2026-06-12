import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

const visibleSourceFiles = [
  'agentWorkspace/AgentChannelInspector.svelte',
  'agentWorkspace/AgentConversationComposer.svelte',
  'agentWorkspace/AgentConversationPane.svelte',
  'agentWorkspace/AgentWorkspaceSidebar.svelte',
  'agentWorkspace/CodexSessionPicker.svelte',
  'agentGroup/CodexTranscriptPanel.svelte'
];

describe('Agent Workspace Chinese copy', () => {
  test('does not show English workspace labels in the desktop UI', () => {
    const source = readVisibleSources();

    for (const snippet of [
      '>Agent Workspace<',
      '>Channels<',
      '>Direct messages<',
      'placeholder="+ New Group"',
      'placeholder="Topic"',
      'placeholder="创建群聊"',
      'placeholder="群聊主题"',
      'placeholder="目标"',
      'aria-label="Workspace conversations"',
      'Private AI chat',
      '>Refresh<',
      'Loading Agent Workspace',
      'No messages yet',
      'Message current group',
      'Message coordinator AI',
      '>Queue<',
      '>Interrupt<',
      '>Send<',
      '>Channel settings<',
      '>Sessions<',
      'Private chat has no channel members.',
      '>Codex sessions<',
      '>Loading<',
      'placeholder="Display name"',
      'placeholder="Role"',
      'placeholder="Goal"',
      '>Add selected Codex<',
      '>Transcript<',
      '>Stop<',
      '>Remove<',
      'Codex transcript',
      '>Raw<',
      '>Readable<'
    ]) {
      expect(source).not.toContain(snippet);
    }
  });

  test('keeps Chinese labels for the main workspace actions', () => {
    const source = readVisibleSources();

    for (const phrase of [
      '智能体工作区',
      '群聊名称',
      '群聊目标/说明（可选）',
      '群聊',
      '私聊',
      '刷新',
      '暂无消息',
      '发送到当前群聊',
      '排队',
      '打断',
      '发送',
      '工作区设置',
      '绑定目录',
      '保存设置',
      '频道设置',
      '会话列表',
      '成员目标/备注（可选）',
      '添加选中的 Codex',
      '查看记录',
      'Codex 会话记录',
      '原始数据',
      '可读视图',
      '停止',
      '移除'
    ]) {
      expect(source).toContain(phrase);
    }
  });
});

function readVisibleSources(): string {
  return visibleSourceFiles.map((fileName) => readSource(fileName)).join('\n');
}

function readSource(fileName: string): string {
  return readFileSync(join(process.cwd(), 'src/lib/components', fileName), 'utf8');
}
