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

  test('keeps the desktop mode switcher out of the header geometry lane', () => {
    const page = readFileSync(join(process.cwd(), 'src/routes/+page.svelte'), 'utf8');
    const styles = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');

    expect(page).toContain('class="iso-desktop-mode-switcher"');
    expect(page).not.toContain('fixed right-4 top-4 z-10 flex gap-2');
    expect(styles).toContain('.iso-desktop-mode-switcher');
    expect(styles).toContain('right: 13rem;');
  });
});
