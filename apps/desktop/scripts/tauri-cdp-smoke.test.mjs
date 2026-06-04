import { describe, expect, test } from 'vitest';
import {
  selectWebViewTarget,
  assertSmokeState,
  runTauriCdpSmoke
} from './tauri-cdp-smoke.mjs';

class FakeWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.sent = [];
    this.closed = false;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  send(message) {
    const payload = JSON.parse(message);
    this.sent.push(payload);
    queueMicrotask(() => {
      const result =
        payload.method === 'Runtime.evaluate'
          ? {
              result: {
                value: {
                  text: 'AI\nCDP automation smoke\nCDP smoke ok\n发送',
                  inputDisabled: false,
                  buttonDisabled: false
                }
              }
            }
          : {};
      this.onmessage?.({ data: JSON.stringify({ id: payload.id, result }) });
    });
  }

  close() {
    this.closed = true;
  }
}

describe('tauri CDP smoke helpers', () => {
  test('selects the requested Tauri WebView target by window query', () => {
    const target = selectWebViewTarget(
      [
        { url: 'http://127.0.0.1:5173/?window=orb', webSocketDebuggerUrl: 'ws://orb' },
        { url: 'http://127.0.0.1:5173/?window=main', webSocketDebuggerUrl: 'ws://main' }
      ],
      'main'
    );

    expect(target.webSocketDebuggerUrl).toBe('ws://main');
  });

  test('rejects smoke state when the expected answer is missing', () => {
    expect(() =>
      assertSmokeState(
        {
          text: 'AI\nstill waiting',
          inputDisabled: false,
          buttonDisabled: false
        },
        { expectedText: 'CDP smoke ok' }
      )
    ).toThrow('expected text was not rendered');
  });

  test('drives the main WebView through CDP and returns DOM smoke state', async () => {
    FakeWebSocket.instances = [];
    const fetchImpl = async (url) => {
      expect(url).toBe('http://127.0.0.1:9223/json/list');
      return {
        ok: true,
        async json() {
          return [
            {
              url: 'http://127.0.0.1:5173/?window=main',
              webSocketDebuggerUrl: 'ws://main'
            }
          ];
        }
      };
    };

    const result = await runTauriCdpSmoke({
      fetchImpl,
      WebSocketCtor: FakeWebSocket,
      cdpBaseUrl: 'http://127.0.0.1:9223',
      question: 'CDP automation smoke',
      expectedText: 'CDP smoke ok',
      settleMs: 0
    });

    expect(result.state.text).toContain('CDP smoke ok');
    expect(result.target.url).toContain('window=main');
    expect(FakeWebSocket.instances[0].closed).toBe(true);
  });
});
