import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CommandComposer', () => {
  test('keeps trimmed submit behavior and disabled guard', () => {
    const path = join(process.cwd(), 'src/lib/components/common/CommandComposer.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('const text = value.trim();');
    expect(source).toContain('if (!text || disabled) return;');
    expect(source).toContain('onSubmit(text);');
    expect(source).toContain("value = '';");
  });

  test('uses shared command composer visual classes', () => {
    const path = join(process.cwd(), 'src/lib/components/common/CommandComposer.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('class="iso-command-composer"');
    expect(source).toContain('class="iso-command-input"');
    expect(source).toContain('class="iso-button-primary"');
  });
});
