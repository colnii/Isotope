import { describe, expect, test } from 'vitest';
import {
  assertScreenArtifactState,
  installActionCaptureExpression,
  runTauriScreenArtifactSmoke
} from './tauri-screen-artifact-smoke.mjs';

class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.closed = false;
    this.evaluateCount = 0;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  send(message) {
    const payload = JSON.parse(message);
    queueMicrotask(() => {
      const result =
        payload.method === 'Runtime.evaluate'
          ? { result: { value: this.nextEvaluationValue(payload.params.expression) } }
          : {};
      this.onmessage?.({ data: JSON.stringify({ id: payload.id, result }) });
    });
  }

  nextEvaluationValue(expression) {
    this.evaluateCount += 1;
    if (expression.includes('img[alt="screen screenshot original"]')) {
      return {
        artifactTitle: 'artifact_005.png',
        image: {
          srcPrefix: 'data:image/png;base64,iVBORw0K',
          srcLength: 128946,
          naturalWidth: 900,
          naturalHeight: 600
        },
        download: {
          download: 'artifact_005.png',
          hrefPrefix: 'data:image/png;base64,iVBORw0K',
          hrefLength: 128946,
          rel: 'noopener'
        },
        folder: {
          command: 'open_path',
          path: 'C:\\Users\\lumber\\AppData\\Local\\Temp\\isotope\\runs\\run_003\\artifacts'
        }
      };
    }
    if (expression.includes('document.body.innerText')) {
      return {
        text: 'AI\n观察屏幕\nscreen screenshot\n原图\n文件夹\n下载\n发送',
        buttons: [
          { text: '+', aria: '展开动作详情' },
          { text: '发送', aria: null }
        ],
        inputDisabled: false,
        buttonDisabled: false
      };
    }
    if (expression.includes('button.click()')) return true;
    if (expression.includes('__isotopeDownloadCaptureInstalled')) return true;
    return true;
  }

  close() {
    this.closed = true;
  }
}

describe('tauri screen artifact CDP smoke', () => {
  test('rejects original image state that is only a small preview', () => {
    expect(() =>
      assertScreenArtifactState({
        artifactTitle: 'artifact_001.png',
        image: {
          srcPrefix: 'data:image/png;base64,iVBORw0K',
          srcLength: 1200,
          naturalWidth: 320,
          naturalHeight: 180
        },
        download: {
          download: 'artifact_001.png',
          hrefPrefix: 'data:image/png;base64,iVBORw0K',
          hrefLength: 1200,
          rel: 'noopener'
        },
        folder: {
          command: 'open_path',
          path: 'C:\\tmp\\artifacts'
        }
      })
    ).toThrow('screen original image data URL is too small');
  });

  test('drives Tauri screen original, download, and folder actions through CDP', async () => {
    FakeWebSocket.instances = [];
    const fetchImpl = async () => ({
      ok: true,
      async json() {
        return [
          {
            url: 'http://127.0.0.1:5173/?window=main',
            webSocketDebuggerUrl: 'ws://main'
          }
        ];
      }
    });

    const result = await runTauriScreenArtifactSmoke({
      fetchImpl,
      WebSocketCtor: FakeWebSocket,
      question: '观察屏幕并打开原图',
      settleMs: 0
    });

    expect(result.state.artifactTitle).toBe('artifact_005.png');
    expect(result.state.image.naturalWidth).toBe(900);
    expect(result.state.download.download).toBe('artifact_005.png');
    expect(result.state.folder.command).toBe('open_path');
    expect(FakeWebSocket.instances[0].closed).toBe(true);
  });

  test('re-wraps Tauri invoke when the runtime replaces the function', async () => {
    const originalCreateElement = document.createElement.bind(document);
    try {
      window.__TAURI_INTERNALS__ = {
        invoke: async () => ({ status: 'real' })
      };

      eval(installActionCaptureExpression());
      await window.__TAURI_INTERNALS__.invoke('open_path', { path: 'C:\\first' });
      expect(window.__isotopeOpenPathCalls).toEqual([{ command: 'open_path', path: 'C:\\first' }]);

      window.__TAURI_INTERNALS__.invoke = async () => ({ status: 'replacement' });
      eval(installActionCaptureExpression());
      await window.__TAURI_INTERNALS__.invoke('open_path', { path: 'C:\\second' });
      expect(window.__isotopeOpenPathCalls).toEqual([{ command: 'open_path', path: 'C:\\second' }]);
    } finally {
      document.createElement = originalCreateElement;
      delete window.__TAURI_INTERNALS__;
      delete window.__isotopeDownloadCaptureInstalled;
      delete window.__isotopeDownloadInfo;
      delete window.__isotopeOpenPathCalls;
    }
  });

  test('captures open_path at the Tauri IPC layer', async () => {
    const originalCreateElement = document.createElement.bind(document);
    const callbacks = [];
    try {
      window.__TAURI_INTERNALS__ = {
        ipc: () => {
          throw new Error('open_path should not reach real IPC');
        },
        runCallback: (id, payload) => callbacks.push({ id, payload })
      };

      eval(installActionCaptureExpression());
      window.__TAURI_INTERNALS__.ipc({
        cmd: 'open_path',
        payload: { path: 'C:\\artifacts' },
        callback: 42
      });
      await new Promise((resolve) => queueMicrotask(resolve));

      expect(window.__isotopeOpenPathCalls).toEqual([{ command: 'open_path', path: 'C:\\artifacts' }]);
      expect(callbacks).toEqual([{ id: 42, payload: { status: 'ok', path: 'C:\\artifacts' } }]);
    } finally {
      document.createElement = originalCreateElement;
      delete window.__TAURI_INTERNALS__;
      delete window.__isotopeDownloadCaptureInstalled;
      delete window.__isotopeDownloadInfo;
      delete window.__isotopeOpenPathCalls;
    }
  });
});
