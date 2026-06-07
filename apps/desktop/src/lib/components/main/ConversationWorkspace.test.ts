import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('ConversationWorkspace', () => {
  test('keeps assistant capacity calls before final answer text in the template', () => {
    const path = join(process.cwd(), 'src/lib/components/main/ConversationWorkspace.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source.indexOf('<CapacityCallCard')).toBeGreaterThan(-1);
    expect(source.indexOf('{message.content}')).toBeGreaterThan(-1);
    expect(source.indexOf('<CapacityCallCard')).toBeLessThan(
      source.indexOf('{message.content}')
    );
  });
});
