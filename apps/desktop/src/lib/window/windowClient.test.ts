import { describe, expect, test, vi } from 'vitest';
import { createWindowClient } from './windowClient';

describe('createWindowClient', () => {
  test('opens a Tauri window with an explicit focus option', async () => {
    const invoke = vi.fn().mockResolvedValue({ label: 'mini', visible: true, focused: true });
    const client = createWindowClient({ invoke, canInvoke: () => true });

    await client.open('mini', { focus: true });

    expect(invoke).toHaveBeenCalledWith('open_window', { label: 'mini', focus: true });
  });

  test('hides a Tauri window by label', async () => {
    const invoke = vi.fn().mockResolvedValue({ label: 'mini', visible: false, focused: false });
    const client = createWindowClient({ invoke, canInvoke: () => true });

    await client.hide('mini');

    expect(invoke).toHaveBeenCalledWith('hide_window', { label: 'mini' });
  });

  test('opens a local folder path through Tauri', async () => {
    const invoke = vi.fn().mockResolvedValue({ status: 'ok', path: 'C:\\tmp\\screen' });
    const client = createWindowClient({ invoke, canInvoke: () => true });

    await client.openPath('C:\\tmp\\screen');

    expect(invoke).toHaveBeenCalledWith('open_path', { path: 'C:\\tmp\\screen' });
  });

  test('uses a no-op result outside the Tauri runtime', async () => {
    const invoke = vi.fn();
    const client = createWindowClient({ invoke, canInvoke: () => false });

    await expect(client.open('mini', { focus: true })).resolves.toEqual({
      label: 'mini',
      visible: true,
      focused: true
    });

    expect(invoke).not.toHaveBeenCalled();
  });

  test('does not expose the native orb as a Tauri window label', () => {
    const labels = ['mini', 'main'] satisfies import('./windowClient').WindowLabel[];

    expect(labels).not.toContain('orb');
  });
});
