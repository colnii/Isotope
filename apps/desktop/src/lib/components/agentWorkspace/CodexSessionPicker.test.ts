import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CodexSessionPicker source contract', () => {
  test('offers cwd and all recent codex session scopes', () => {
    const source = readSource('CodexSessionPicker.svelte');

    expect(source).toContain("sessionScope = 'cwd'");
    expect(source).toContain("sessionScope = 'all'");
    expect(source).toContain('onLoadCodexSessions(sessionScope)');
  });

  test('keeps add-member fields and send policy visible', () => {
    const source = readSource('CodexSessionPicker.svelte');

    expect(source).toContain('memberDisplayName');
    expect(source).toContain('memberRole');
    expect(source).toContain('memberGoal');
    expect(source).toContain('memberSendPolicy');
    expect(source).toContain('添加选中的 Codex');
  });
});

function readSource(fileName: string): string {
  return readFileSync(join(process.cwd(), 'src/lib/components/agentWorkspace', fileName), 'utf8');
}
