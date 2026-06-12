import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('AgentWorkspaceShell', () => {
  test('keeps a channel and DM sidebar with creation entry', () => {
    const source = readSources('AgentWorkspaceShell.svelte', 'AgentWorkspaceSidebar.svelte');

    expect(source).toContain('createChannel');
    expect(source).toContain('群聊');
    expect(source).toContain('私聊');
    expect(source).toContain('selectedConversationKind');
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
    expect(source).toContain('removeMember');
    expect(source).toContain('send_policy');
    expect(source).toContain('loadTranscript');
    expect(source).toContain('CodexTranscriptPanel');
    expect(source).toContain('Math.max(policyLimit, 1000)');
    expect(source).toContain('candidate.display_title || candidate.title');
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
});

function readSources(...fileNames: string[]): string {
  return fileNames.map((fileName) => readSource(fileName)).join('\n');
}

function readSource(fileName: string): string {
  return readFileSync(join(process.cwd(), 'src/lib/components/agentWorkspace', fileName), 'utf8');
}
