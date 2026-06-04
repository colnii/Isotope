import { invoke, isTauri } from '@tauri-apps/api/core';

export type WindowLabel = 'mini' | 'main';

export type OpenWindowOptions = {
  focus?: boolean;
};

export type WindowCommandResult = {
  label: WindowLabel;
  visible: boolean;
  focused: boolean;
};

export type OpenPathResult = {
  status: 'ok' | 'noop';
  path: string;
};

type InvokeFn = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;

type WindowClientOptions = {
  invoke?: InvokeFn;
  canInvoke?: () => boolean;
};

const noopResult = (label: WindowLabel, visible: boolean, focused = false): WindowCommandResult => ({
  label,
  visible,
  focused
});

export function createWindowClient(options: WindowClientOptions = {}) {
  const invokeFn = options.invoke ?? invoke;
  const canInvoke = options.canInvoke ?? isTauri;

  return {
    open(label: WindowLabel, options: OpenWindowOptions = {}) {
      if (!canInvoke()) return Promise.resolve(noopResult(label, true, options.focus === true));
      return invokeFn<WindowCommandResult>('open_window', { label, focus: options.focus });
    },

    hide(label: WindowLabel) {
      if (!canInvoke()) return Promise.resolve(noopResult(label, false));
      return invokeFn<WindowCommandResult>('hide_window', { label });
    },

    openPath(path: string) {
      if (!canInvoke()) return Promise.resolve({ status: 'noop' as const, path });
      return invokeFn<OpenPathResult>('open_path', { path });
    }
  };
}

export const windowClient = createWindowClient();
