import { isTauri } from '@tauri-apps/api/core';
import { getCurrentWindow } from '@tauri-apps/api/window';

type DragWindow = {
  startDragging(): Promise<void>;
};

type WindowDragClientOptions = {
  canDrag?: () => boolean;
  getCurrentWindow?: () => DragWindow;
};

export function createWindowDragClient(options: WindowDragClientOptions = {}) {
  const canDrag = options.canDrag ?? isTauri;
  const currentWindow = options.getCurrentWindow ?? getCurrentWindow;

  return {
    async startDragging() {
      if (!canDrag()) return false;
      await currentWindow().startDragging();
      return true;
    }
  };
}

export const windowDragClient = createWindowDragClient();
