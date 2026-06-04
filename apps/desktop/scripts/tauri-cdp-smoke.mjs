#!/usr/bin/env node

import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);

export function selectWebViewTarget(targets, windowName = 'main') {
  const expectedQuery = `window=${encodeURIComponent(windowName)}`;
  const target = targets.find(
    (item) =>
      typeof item?.url === 'string' &&
      item.url.includes(expectedQuery) &&
      typeof item.webSocketDebuggerUrl === 'string'
  );
  if (!target) {
    const urls = targets.map((item) => item?.url).filter(Boolean).join(', ') || 'none';
    throw new Error(`Tauri WebView target not found for ${expectedQuery}; available targets: ${urls}`);
  }
  return target;
}

export function assertSmokeState(state, { expectedText }) {
  if (!state || typeof state !== 'object') {
    throw new Error('CDP smoke did not return DOM state');
  }
  if (typeof state.text !== 'string' || !state.text.includes(expectedText)) {
    throw new Error(`expected text was not rendered: ${expectedText}`);
  }
  if (state.inputDisabled === true) {
    throw new Error('composer input stayed disabled after chat response');
  }
  if (state.buttonDisabled === true) {
    throw new Error('composer submit button stayed disabled after chat response');
  }
}

export async function runTauriCdpSmoke({
  cdpBaseUrl = 'http://127.0.0.1:9223',
  windowName = 'main',
  question = 'CDP automation smoke',
  expectedText = 'CDP smoke ok',
  timeoutMs = 10000,
  settleMs = 250,
  fetchImpl = globalThis.fetch,
  WebSocketCtor = globalThis.WebSocket
} = {}) {
  if (typeof fetchImpl !== 'function') {
    throw new Error('global fetch is unavailable; use Node 18+ or pass fetchImpl');
  }
  if (typeof WebSocketCtor !== 'function') {
    throw new Error('global WebSocket is unavailable; use Node 22+ or pass WebSocketCtor');
  }

  const targets = await fetchTargets(cdpBaseUrl, fetchImpl);
  const target = selectWebViewTarget(targets, windowName);
  const session = await connectCdp(target.webSocketDebuggerUrl, WebSocketCtor);
  try {
    await session.send('Runtime.enable');
    await session.evaluate(fillAndSubmitExpression(question));
    const state = await waitForSmokeState(session, { expectedText, timeoutMs, settleMs });
    return { target, state };
  } finally {
    session.close();
  }
}

async function fetchTargets(cdpBaseUrl, fetchImpl) {
  const url = `${cdpBaseUrl.replace(/\/$/, '')}/json/list`;
  const response = await fetchImpl(url);
  if (!response.ok) {
    throw new Error(`CDP target list request failed: HTTP ${response.status}`);
  }
  const targets = await response.json();
  if (!Array.isArray(targets)) {
    throw new Error('CDP target list response was not an array');
  }
  return targets;
}

function connectCdp(webSocketDebuggerUrl, WebSocketCtor) {
  const socket = new WebSocketCtor(webSocketDebuggerUrl);
  let sequence = 0;
  const pending = new Map();

  socket.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve: resolvePending, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) {
      reject(new Error(JSON.stringify(message.error)));
      return;
    }
    resolvePending(message.result ?? {});
  };

  const opened = new Promise((resolveOpened, reject) => {
    socket.onopen = resolveOpened;
    socket.onerror = reject;
  });

  return opened.then(() => ({
    send(method, params = {}) {
      const id = ++sequence;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolvePending, reject) => {
        pending.set(id, { resolve: resolvePending, reject });
      });
    },
    async evaluate(expression) {
      const result = await this.send('Runtime.evaluate', {
        expression,
        awaitPromise: true,
        returnByValue: true
      });
      if (result.exceptionDetails) {
        throw new Error(`CDP Runtime.evaluate failed: ${JSON.stringify(result.exceptionDetails)}`);
      }
      return result.result?.value;
    },
    close() {
      socket.close();
    }
  }));
}

async function waitForSmokeState(session, { expectedText, timeoutMs, settleMs }) {
  const startedAt = Date.now();
  let lastState = null;
  let lastError = null;
  while (Date.now() - startedAt <= timeoutMs) {
    if (settleMs > 0) {
      await new Promise((resolvePromise) => setTimeout(resolvePromise, settleMs));
    }
    lastState = await session.evaluate(readStateExpression());
    try {
      assertSmokeState(lastState, { expectedText });
      return lastState;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error(`CDP smoke timed out after ${timeoutMs}ms`);
}

function fillAndSubmitExpression(question) {
  return `(() => {
    const input = document.querySelector('input');
    const button = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.trim() === '发送');
    if (!input || !button) {
      throw new Error('composer not found');
    }
    input.value = ${JSON.stringify(question)};
    input.dispatchEvent(new Event('input', { bubbles: true }));
    button.click();
    return true;
  })()`;
}

function readStateExpression() {
  return `(() => {
    const submitButton = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.trim() === '发送');
    return {
      text: document.body.innerText,
      inputDisabled: document.querySelector('input')?.disabled ?? null,
      buttonDisabled: submitButton?.disabled ?? null
    };
  })()`;
}

async function main() {
  const result = await runTauriCdpSmoke({
    cdpBaseUrl: process.env.ISOTOPE_TAURI_CDP_URL || 'http://127.0.0.1:9223',
    windowName: process.env.ISOTOPE_TAURI_CDP_WINDOW || 'main',
    question: process.env.ISOTOPE_TAURI_CDP_QUESTION || 'CDP automation smoke',
    expectedText: process.env.ISOTOPE_TAURI_CDP_EXPECTED || 'CDP smoke ok',
    timeoutMs: Number(process.env.ISOTOPE_TAURI_CDP_TIMEOUT_MS || 10000)
  });
  console.log(
    JSON.stringify(
      {
        status: 'ok',
        target: {
          url: result.target.url,
          title: result.target.title
        },
        state: {
          inputDisabled: result.state.inputDisabled,
          buttonDisabled: result.state.buttonDisabled
        }
      },
      null,
      2
    )
  );
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
