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
});
