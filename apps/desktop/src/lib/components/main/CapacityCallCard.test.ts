import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('CapacityCallCard visual contract', () => {
  test('uses shared capacity card shell and status classes', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallCard.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('const capacityToneClass = $derived(');
    expect(source).toContain('const capacityStatusDotClass = $derived(');
    expect(source).toContain('class="iso-capacity-card"');
    expect(source).toContain('iso-capacity-status-dot');
    expect(source).toContain('iso-status-chip');
    expect(source).toContain('iso-capacity-actions');
    expect(source.indexOf('iso-capacity-status-dot')).toBeLessThan(source.indexOf('{statusLabel}'));
  });

  test('keeps existing action entry points inside the restyled shell', () => {
    const path = join(process.cwd(), 'src/lib/components/main/CapacityCallCard.svelte');
    const source = readFileSync(path, 'utf8');

    expect(source).toContain('onclick={toggleExpanded}');
    expect(source).toContain('onclick={openFullscreen}');
    expect(source).toContain('onclick={() => viewOriginal(screenArtifacts[0].artifactId)}');
    expect(source).toContain('onclick={() => openArtifactFolder(screenArtifacts[0].artifactId)}');
    expect(source).toContain('onclick={() => downloadArtifact(screenArtifacts[0].artifactId)}');
    expect(source).toContain('class="iso-button-muted"');
    expect(source).toContain('<CapacityCallDetails details={call.details} />');
  });
});
