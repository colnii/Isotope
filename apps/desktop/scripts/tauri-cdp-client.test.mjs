import { describe, expect, test } from 'vitest';
import {
  connectCdp,
  evaluate,
  selectWebViewTarget
} from './tauri-cdp-client.mjs';

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
          ? { result: { value: { ok: true, expression: payload.params.expression } } }
          : {};
      this.onmessage?.({ data: JSON.stringify({ id: payload.id, result }) });
    });
  }

  close() {
    this.closed = true;
  }
}

describe('tauri CDP client helpers', () => {
  test('selects WebView target by Tauri window query', () => {
    const target = selectWebViewTarget(
      [
        { url: 'http://127.0.0.1:5173/?window=orb', webSocketDebuggerUrl: 'ws://orb' },
        { url: 'http://127.0.0.1:5173/?window=main', webSocketDebuggerUrl: 'ws://main' }
      ],
      'main'
    );

    expect(target.webSocketDebuggerUrl).toBe('ws://main');
  });

  test('connects, evaluates, and closes a CDP session', async () => {
    FakeWebSocket.instances = [];
    const session = await connectCdp('ws://main', FakeWebSocket);

    const value = await evaluate(session, '(() => true)()');
    session.close();

    expect(value).toEqual({ ok: true, expression: '(() => true)()' });
    expect(FakeWebSocket.instances[0].closed).toBe(true);
  });
});
