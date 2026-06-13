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

  test('places the desktop mode switcher in a fixed left rail', () => {
    const page = readFileSync(join(process.cwd(), 'src/routes/+page.svelte'), 'utf8');
    const styles = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');

    expect(page).toContain("from '$lib/components/common/DesktopModeRail.svelte';");
    expect(page).toContain('<DesktopModeRail mode={desktopMode}');
    expect(page).toContain('class="iso-desktop-workspace-with-rail"');
    expect(page).not.toContain('iso-desktop-mode-switcher');
    expect(styles).toContain('.iso-desktop-mode-rail');
    expect(styles).toContain('width: 5.25rem;');
    expect(styles).toContain('.iso-desktop-workspace-with-rail');
    expect(styles).toContain('padding-left: 5.25rem;');
  });
});
