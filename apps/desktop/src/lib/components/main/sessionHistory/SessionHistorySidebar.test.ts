import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('SessionHistorySidebar', () => {
  test('renders a left sidebar with session actions and selectable sessions', () => {
    const path = join(
      process.cwd(),
      'src/lib/components/main/sessionHistory/SessionHistorySidebar.svelte'
    );
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('<aside class="iso-session-sidebar"');
    expect(source).toContain('历史会话');
    expect(source).toContain('aria-label="新建会话"');
    expect(source).toContain('{#each sessions as session (session.id)}');
    expect(source).toContain('onclick={() => onSelectSession(session.id)}');
  });
});
