#!/usr/bin/env node

import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  connectTauriWebView,
  evaluate,
  selectWebViewTarget,
  waitForState
} from './tauri-cdp-client.mjs';

const scriptPath = fileURLToPath(import.meta.url);

export { selectWebViewTarget };

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

  const { target, session } = await connectTauriWebView({
    cdpBaseUrl,
    windowName,
    fetchImpl,
    WebSocketCtor
  });
  try {
    await evaluate(session, fillAndSubmitExpression(question));
    const state = await waitForState(
      session,
      readStateExpression(),
      (value) => assertSmokeState(value, { expectedText }),
      { timeoutMs, settleMs }
    );
    return { target, state };
  } finally {
    session.close();
  }
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
