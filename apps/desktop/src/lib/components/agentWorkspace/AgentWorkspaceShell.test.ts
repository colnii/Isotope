import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('AgentWorkspaceShell', () => {
  test('keeps a channel and DM sidebar with creation entry', () => {
    const source = readSources(
      'AgentWorkspaceShell.svelte',
      'AgentWorkspaceSidebar.svelte',
      'AgentConversationPane.svelte'
    );

    expect(source).toContain('createChannel');
    expect(source).toContain('群聊');
    expect(source).toContain('私聊');
    expect(source).toContain('selectedConversationKind');
    expect(source).toContain('conversationSubtitle');
    expect(source).toContain('channel.topic.trim()');
    expect(source).toContain('工作区设置');
    expect(source).toContain('绑定目录');
    expect(source).toContain('保存设置');
    expect(source).toContain('updateWorkspace');
  });

  test('contains channel settings for codex session membership and send permission', () => {
    const source = readSources(
      'AgentWorkspaceShell.svelte',
      'AgentChannelInspector.svelte',
      'CodexSessionPicker.svelte'
    );

    expect(source).toContain('listCodexSessions');
    expect(source).toContain("sessionScope = 'cwd'");
    expect(source).toContain("sessionScope = 'all'");
    expect(source).toContain('addMember');
    expect(source).toContain('updateMember');
    expect(source).toContain('reactivateMember');
    expect(source).toContain('removeMember');
    expect(source).toContain('send_policy');
    expect(source).toContain('loadTranscript');
    expect(source).toContain('CodexTranscriptPanel');
    expect(source).toContain('Math.max(policyLimit, 1000)');
    expect(source).toContain('candidate.display_title || candidate.title');
    expect(source).toContain("status: 'active'");
    expect(source).toContain('启用');
  });

  test('routes composer intent between conversation chat and stop controls', () => {
    const source = readSources('AgentWorkspaceShell.svelte', 'AgentConversationComposer.svelte');

    expect(source).toContain('sendConversation');
    expect(source).toContain('stopCurrentRun');
    expect(source).toContain('stopMember');
    expect(source).toContain('排队');
    expect(source).toContain('打断');
    expect(source).toContain('停止');
  });

  test('renders member observations with member display names', () => {
    const source = readSources('AgentWorkspaceShell.svelte', 'AgentConversationPane.svelte');

    expect(source).toContain('{currentMembers}');
    expect(source).toContain('actorDisplayName');
    expect(source).toContain("member.member_id === actorId");
    expect(source).toContain("return '我'");
    expect(source).toContain("return '系统'");
  });

  test('hides supervisor delivery status messages from the chat stream', () => {
    const source = readSources('AgentWorkspaceShell.svelte');

    expect(source).toContain('visibleConversationMessages');
    expect(source).toContain("message.message_type !== 'sent_to_member'");
    expect(source).toContain("message.message_type !== 'status'");
  });

  test('uses shared canvas suprematist classes for the group chat surface', () => {
    const source = readSources(
      'AgentWorkspaceShell.svelte',
      'AgentWorkspaceSidebar.svelte',
      'AgentConversationPane.svelte',
      'AgentConversationComposer.svelte',
      'AgentChannelInspector.svelte',
      'CodexSessionPicker.svelte'
    );
    const styles = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');

    for (const className of [
      'iso-agent-workspace-shell',
      'iso-agent-sidebar',
      'iso-agent-sidebar-header',
      'iso-agent-panel',
      'iso-agent-pane',
      'iso-agent-pane-header',
      'iso-agent-stream',
      'iso-agent-message',
      'iso-agent-composer',
      'iso-agent-input',
      'iso-agent-inspector',
      'iso-agent-button-primary'
    ]) {
      expect(source).toContain(className);
      expect(styles).toContain(`.${className}`);
    }

    expect(source).not.toContain('bg-[#f6f7f9]');
    expect(source).not.toContain('bg-[#eef2f6]');
    expect(source).not.toContain('bg-[#fbfcfd]');
  });
});

function readSources(...fileNames: string[]): string {
  return fileNames.map((fileName) => readSource(fileName)).join('\n');
}

function readSource(fileName: string): string {
  return readFileSync(join(process.cwd(), 'src/lib/components/agentWorkspace', fileName), 'utf8');
}
