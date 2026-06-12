import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('desktop page Agent Workspace entry', () => {
  test('uses the real Agent Workspace shell instead of the old fixture', () => {
    const page = readFileSync(join(process.cwd(), 'src/routes/+page.svelte'), 'utf8');

    expect(page).toContain('AgentWorkspaceShell');
    expect(page).toContain('agentWorkspaceClient');
    expect(page).not.toContain('agentGroupFixture');
  });
});
