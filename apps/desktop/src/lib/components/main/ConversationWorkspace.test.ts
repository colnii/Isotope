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

describe('CapacityCallDetails', () => {
  test('renders raw detail JSON only after a details section is opened', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallDetails.svelte');
    const source = readFileSync(path, 'utf8');
    const openBindingIndex = source.indexOf('bind:open');
    const rawPreIndex = source.indexOf('{formatCapacityDetailContent(section)}');

    expect(openBindingIndex).toBeGreaterThan(-1);
    expect(rawPreIndex).toBeGreaterThan(-1);
    expect(openBindingIndex).toBeLessThan(rawPreIndex);
    expect(source).toContain('{#if openSections[index]}');
  });
});
