import { describe, expect, test } from 'vitest';
import {
  buildObserveCommand,
  buildObservePlan,
  parseObserveArgs
} from './desktop-observe.mjs';

describe('desktop observe launcher', () => {
  test('defaults to the CDP smoke path', () => {
    const command = buildObserveCommand('cdp', {
      nodeCommand: 'node-test',
      scriptDir: '/repo/apps/desktop/scripts'
    });

    expect(command.argv).toEqual([
      'node-test',
      '/repo/apps/desktop/scripts/tauri-cdp-smoke.mjs'
    ]);
    expect(command.mode).toBe('cdp');
  });

  test('selects the screen artifact smoke from CLI mode', () => {
    const parsed = parseObserveArgs(['--mode', 'screen'], {});
    const command = buildObserveCommand(parsed.mode, {
      nodeCommand: 'node-test',
      scriptDir: '/repo/apps/desktop/scripts'
    });

    expect(command.argv).toEqual([
      'node-test',
      '/repo/apps/desktop/scripts/tauri-screen-artifact-smoke.mjs'
    ]);
  });

  test('builds a machine-readable plan for agents', () => {
    const plan = buildObservePlan({
      nodeCommand: 'node-test',
      scriptDir: '/repo/apps/desktop/scripts'
    });

    expect(plan.defaultMode).toBe('cdp');
    expect(plan.modes.cdp.command).toEqual([
      'node-test',
      '/repo/apps/desktop/scripts/tauri-cdp-smoke.mjs'
    ]);
    expect(plan.modes.screen.command).toEqual([
      'node-test',
      '/repo/apps/desktop/scripts/tauri-screen-artifact-smoke.mjs'
    ]);
    expect(plan.setup).toContain('npm run dev:full');
  });

  test('rejects unknown observe modes with available options', () => {
    expect(() => parseObserveArgs(['--mode=video'], {})).toThrow(
      'desktop observe mode must be one of: cdp, screen'
    );
  });
});
