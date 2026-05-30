import { describe, expect, test, vi } from 'vitest';
import { createWindowDragClient } from './windowDragClient';

describe('createWindowDragClient', () => {
  test('starts dragging the current Tauri window', async () => {
    const startDragging = vi.fn().mockResolvedValue(undefined);
    const client = createWindowDragClient({
      canDrag: () => true,
      getCurrentWindow: () => ({ startDragging })
    });

    await expect(client.startDragging()).resolves.toBe(true);

    expect(startDragging).toHaveBeenCalledOnce();
  });

  test('does nothing outside the Tauri runtime', async () => {
    const startDragging = vi.fn();
    const client = createWindowDragClient({
      canDrag: () => false,
      getCurrentWindow: () => ({ startDragging })
    });

    await expect(client.startDragging()).resolves.toBe(false);

    expect(startDragging).not.toHaveBeenCalled();
  });
});
