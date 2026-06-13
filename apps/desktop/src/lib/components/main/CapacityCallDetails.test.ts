import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CapacityCallDetails visual contract', () => {
  test('uses raised cards and bounded canvas raw content areas', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallDetails.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('class="iso-card-raised');
    expect(source).toContain('bg-isotope-canvas');
    expect(source).toContain('rounded-panel');
    expect(source).toContain("fullscreen ? 'max-h-[70vh]' : 'max-h-64'");
  });

  test('keeps research source links readable with the blue accent', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallDetails.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('text-isotope-blue');
    expect(source).toContain('researchSourcePreviewsForDetailSection(section)');
    expect(source).toContain('{source.url}');
  });

  test('renders research recall previews before raw json disclosure', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallDetails.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('researchRecallPreviewsForDetailSection(section)');
    expect(source).toContain('{preview.summary}');
    expect(source).toContain('{preview.artifactId}');
    expect(source).toContain('{preview.runId}');
    expect(source).toContain('结果原文');
  });
});
