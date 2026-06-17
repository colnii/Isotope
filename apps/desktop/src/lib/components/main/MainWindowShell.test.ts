import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('MainWindowShell', () => {
  test('mounts session history sidebar to the left of the conversation workspace', () => {
    const path = join(process.cwd(), 'src/lib/components/main/MainWindowShell.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain("import SessionHistorySidebar from './sessionHistory/SessionHistorySidebar.svelte'");
    expect(source).toContain('<section class="iso-main-window-shell"');
    expect(source).toContain('<SessionHistorySidebar');
    expect(source).toContain('sessions={chatSessionSummaries}');
    expect(source).toContain('activeSessionId={activeChatSessionId}');
    expect(source).toContain('onSelectSession={onSelectChatSession}');
    expect(source).toContain('onNewSession={onNewChatSession}');
    expect(source.indexOf('<SessionHistorySidebar')).toBeLessThan(
      source.indexOf('<ConversationWorkspace')
    );
  });
});
