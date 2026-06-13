import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('DesktopModeRail', () => {
  test('renders accessible chat and group mode controls', () => {
    const path = join(process.cwd(), 'src/lib/components/common/DesktopModeRail.svelte');

    expect(existsSync(path)).toBe(true);

    const source = readFileSync(path, 'utf8');
    expect(source).toContain('aria-label="桌面模式切换"');
    expect(source).toContain("onclick={() => onModeChange('chat')}");
    expect(source).toContain("onclick={() => onModeChange('agent-workspace')}");
    expect(source).toContain("aria-pressed={mode === 'chat'}");
    expect(source).toContain("aria-pressed={mode === 'agent-workspace'}");
  });

  test('uses left rail visual classes instead of header pill buttons', () => {
    const path = join(process.cwd(), 'src/lib/components/common/DesktopModeRail.svelte');

    expect(existsSync(path)).toBe(true);

    const source = readFileSync(path, 'utf8');
    expect(source).toContain('class="iso-desktop-mode-rail"');
    expect(source).toContain('iso-desktop-mode-button');
    expect(source).toContain('iso-desktop-mode-glyph');
    expect(source).toContain('iso-desktop-mode-label');

    const styles = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');
    expect(styles).toContain('bg-isotope-rail');
    expect(styles).not.toContain('bg-isotope-ink px-3 py-4');
  });
});
