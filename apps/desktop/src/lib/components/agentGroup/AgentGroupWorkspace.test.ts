import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

describe('AgentGroupWorkspace', () => {
  test('contains two-layer stop controls', () => {
    const workspace = readSource('AgentGroupWorkspace.svelte');
    const memberStrip = readSource('AgentGroupMemberStrip.svelte');

    expect(workspace).toContain('Stop current run');
    expect(workspace).toContain('isRunning && composerIsEmpty');
    expect(memberStrip).toContain('Stop ${member.display_name}');
    expect(memberStrip).toContain('onStopMember(member.member_id)');
  });

  test('contains queue and interrupt controls while composer has text during a run', () => {
    const workspace = readSource('AgentGroupWorkspace.svelte');

    expect(workspace).toContain('Queue');
    expect(workspace).toContain('Interrupt');
    expect(workspace).toContain("{:else if isRunning}");
  });

  test('uses shared canvas classes for the direct group chat surface', () => {
    const source = [
      readSource('AgentGroupWorkspace.svelte'),
      readSource('AgentGroupMemberStrip.svelte'),
      readSource('AgentGroupStream.svelte'),
      readSource('AgentGroupPrivateChat.svelte')
    ].join('\n');
    const styles = readFileSync(join(process.cwd(), 'src/app.css'), 'utf8');

    for (const className of [
      'iso-agent-group-shell',
      'iso-agent-member-strip',
      'iso-agent-stream',
      'iso-agent-message',
      'iso-agent-composer',
      'iso-agent-input'
    ]) {
      expect(source).toContain(className);
      expect(styles).toContain(`.${className}`);
    }

    expect(source).not.toContain('bg-white text-isotope-text');
  });
});

function readSource(fileName: string): string {
  return readFileSync(
    join(process.cwd(), 'src/lib/components/agentGroup', fileName),
    'utf8'
  );
}
