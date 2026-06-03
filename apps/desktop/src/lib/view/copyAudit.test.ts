import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, test } from 'vitest';

const visibleCopyFiles = [
  'src/routes/+page.svelte',
  'src/lib/client/agentClient.ts',
  'src/lib/components/orb/FloatingOrb.svelte'
];

const forbiddenVisibleCopy = [
  'Failed to load desktop snapshot.',
  'Question must not be empty',
  'Open Isotope chat',
  'Open MiniWindow',
  'Isotope floating orb preview'
];

describe('desktop visible copy audit', () => {
  test('keeps remaining desktop fallback copy in Chinese', () => {
    const sourceText = visibleCopyFiles
      .map((filePath) => readFileSync(resolve(process.cwd(), filePath), 'utf8'))
      .join('\n');

    for (const phrase of forbiddenVisibleCopy) {
      expect(sourceText).not.toContain(phrase);
    }
  });
});
