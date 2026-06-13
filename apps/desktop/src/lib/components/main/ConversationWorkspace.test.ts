import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('ConversationWorkspace', () => {
  test('renders assistant message parts before falling back to aggregated content', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source.indexOf('{#each message.parts as part')).toBeGreaterThan(-1);
    expect(source.indexOf('call={part.call}')).toBeGreaterThan(-1);
    expect(source.indexOf('{part.text}')).toBeGreaterThan(-1);
    expect(source.indexOf('{message.content}')).toBeGreaterThan(-1);
    expect(source.indexOf('{#each message.parts as part')).toBeLessThan(
      source.indexOf('{message.content}')
    );
  });

  test('contains local file read approval detail branch', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain("tool === 'local_file_read'");
    expect(source).toContain('最多 ${maxExcerptChars} 字符');
  });

  test('contains screen control approval detail branch', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain("tool === 'screen_control'");
    expect(source).toContain('屏幕操作');
    expect(source).toContain('actionTypes');
    expect(source).toContain('selectorKeys');
  });

  test('keeps header copy separated from the suprematist mark', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('<section class="iso-chat-shell"');
    expect(source).toContain('<header class="iso-chat-header">');
    expect(source).toContain('<div class="iso-chat-header-copy">');
    expect(source).toContain('<div class="iso-suprematist-mark" aria-hidden="true">');
    expect(source).toContain('class="iso-suprematist-square"');
    expect(source).toContain('class="iso-chat-subtitle"');
    expect(source.indexOf('<div class="iso-chat-header-copy">')).toBeLessThan(
      source.indexOf('<div class="iso-suprematist-mark" aria-hidden="true">')
    );
  });

  test('uses a connected suprematist header mark with non-rectangular shape', () => {
    const componentPath = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const stylesPath = join(process.cwd(), 'src/app.css');
    const source = readFileSync(componentPath, 'utf8');
    const styles = readFileSync(stylesPath, 'utf8');

    expect(source).toContain('class="iso-suprematist-ring"');
    expect(source).toContain('class="iso-suprematist-link"');
    expect(styles).toContain('border-isotope-umber');
    expect(styles).toContain('border-radius: 9999px;');
    expect(styles).toContain('transform: rotate(-34deg);');
  });

  test('uses shared visual classes for conversation surfaces', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('class="iso-chat-scroll"');
    expect(source).toContain('class="iso-approval-card"');
    expect(source).toContain('iso-message-avatar');
    expect(source).toContain('iso-message-bubble');
    expect(source).toContain('iso-message-bubble-user');
    expect(source).toContain('iso-message-bubble-assistant');
    expect(source).toContain('class="iso-error-card"');
  });

  test('contains terminal approval controls for yolo, single approval, and allowlist', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('terminalYoloEnabled');
    expect(source).toContain('onToggleTerminalYolo');
    expect(source).toContain('本次批准');
    expect(source).toContain('加入 allowlist');
    expect(source).toContain('onAllowlistTerminalApproval');
  });
});
