#!/usr/bin/env node

import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  connectTauriWebView,
  evaluate,
  waitForState
} from './tauri-cdp-client.mjs';

const scriptPath = fileURLToPath(import.meta.url);
const DEFAULT_MIN_DATA_URL_LENGTH = 20_000;
const DEFAULT_MIN_WIDTH = 640;
const DEFAULT_MIN_HEIGHT = 360;

export function assertScreenArtifactState(
  state,
  {
    minDataUrlLength = DEFAULT_MIN_DATA_URL_LENGTH,
    minWidth = DEFAULT_MIN_WIDTH,
    minHeight = DEFAULT_MIN_HEIGHT,
    requireFolder = true
  } = {}
) {
  if (!state || typeof state !== 'object') {
    throw new Error('screen artifact smoke did not return DOM state');
  }
  if (typeof state.artifactTitle !== 'string' || !/^artifact_.+\.png$/.test(state.artifactTitle)) {
    throw new Error(`screen artifact title was not rendered: ${state.artifactTitle ?? 'missing'}`);
  }
  if (!state.image || typeof state.image !== 'object') {
    throw new Error('screen original image was not rendered');
  }
  if (state.image.srcPrefix !== 'data:image/png;base64,iVBORw0K') {
    throw new Error(`screen original image is not a PNG data URL: ${state.image.srcPrefix ?? 'missing'}`);
  }
  if (typeof state.image.srcLength !== 'number' || state.image.srcLength < minDataUrlLength) {
    throw new Error(`screen original image data URL is too small: ${state.image.srcLength ?? 'missing'}`);
  }
  if (state.image.naturalWidth < minWidth || state.image.naturalHeight < minHeight) {
    throw new Error(`screen original image dimensions are too small: ${state.image.naturalWidth}x${state.image.naturalHeight}`);
  }
  if (!state.download || typeof state.download !== 'object') {
    throw new Error('screen artifact download action did not run');
  }
  if (state.download.download !== state.artifactTitle) {
    throw new Error(`download filename did not match artifact title: ${state.download.download ?? 'missing'}`);
  }
  if (state.download.hrefPrefix !== 'data:image/png;base64,iVBORw0K') {
    throw new Error(`download href is not a PNG data URL: ${state.download.hrefPrefix ?? 'missing'}`);
  }
  if (typeof state.download.hrefLength !== 'number' || state.download.hrefLength < minDataUrlLength) {
    throw new Error(`download data URL is too small: ${state.download.hrefLength ?? 'missing'}`);
  }
  if (state.download.rel !== 'noopener') {
    throw new Error(`download anchor rel was not noopener: ${state.download.rel ?? 'missing'}`);
  }
  if (requireFolder) {
    if (!state.folder || typeof state.folder !== 'object') {
      throw new Error('screen artifact folder action did not run');
    }
    if (state.folder.command !== 'open_path') {
      throw new Error(`folder action did not invoke open_path: ${state.folder.command ?? 'missing'}`);
    }
    if (typeof state.folder.path !== 'string' || !state.folder.path.trim()) {
      throw new Error('folder action did not include an artifact directory path');
    }
  }
}

export async function runTauriScreenArtifactSmoke({
  cdpBaseUrl = 'http://127.0.0.1:9223',
  windowName = 'main',
  question = '观察屏幕并打开原图',
  timeoutMs = 30000,
  settleMs = 250,
  fetchImpl = globalThis.fetch,
  WebSocketCtor = globalThis.WebSocket,
  minDataUrlLength = DEFAULT_MIN_DATA_URL_LENGTH,
  minWidth = DEFAULT_MIN_WIDTH,
  minHeight = DEFAULT_MIN_HEIGHT
} = {}) {
  const { target, session } = await connectTauriWebView({
    cdpBaseUrl,
    windowName,
    fetchImpl,
    WebSocketCtor
  });
  try {
    await evaluate(session, installActionCaptureExpression());
    await evaluate(session, submitQuestionExpression(question));
    await waitForState(
      session,
      readBodyTextExpression(),
      (state) => {
        if (!state?.buttons?.some((button) => button.aria === '展开动作详情')) {
          throw new Error('screen.observe action card was not rendered yet');
        }
        if (state.inputDisabled === true || state.buttonDisabled === true) {
          throw new Error('chat composer is still waiting for the screen action response');
        }
      },
      { timeoutMs, settleMs }
    );
    await evaluate(session, clickButtonExpression('展开动作详情'));
    await waitForState(
      session,
      readBodyTextExpression(),
      (state) => {
        if (!state?.text?.includes('原图')) {
          throw new Error('screen artifact original-image action was not rendered yet');
        }
      },
      { timeoutMs, settleMs }
    );
    await evaluate(session, clickButtonExpression('原图'));
    await waitForState(
      session,
      readScreenImageStateExpression(),
      (state) => {
        if (!state?.artifactTitle || !state?.image) {
          throw new Error('screen original image dialog was not rendered yet');
        }
      },
      { timeoutMs, settleMs }
    );
    await evaluate(session, clickDialogButtonExpression('下载'));
    await evaluate(session, installActionCaptureExpression());
    await evaluate(session, clickDialogButtonExpression('文件夹'));
    const state = await waitForState(
      session,
      readScreenArtifactStateExpression(),
      (value) =>
        assertScreenArtifactState(value, {
          minDataUrlLength,
          minWidth,
          minHeight
        }),
      { timeoutMs, settleMs }
    );
    return { target, state };
  } finally {
    session.close();
  }
}

export function installActionCaptureExpression() {
  return `(() => {
    if (!window.__isotopeDownloadCaptureInstalled) {
      const originalCreateElement = document.createElement.bind(document);
      window.__isotopeDownloadInfo = null;
      window.__isotopeDownloadCaptureInstalled = true;
      document.createElement = function(tagName, options) {
        const element = originalCreateElement(tagName, options);
        if (String(tagName).toLowerCase() === 'a') {
          const originalClick = element.click.bind(element);
          element.click = function() {
            window.__isotopeDownloadInfo = {
              download: element.download,
              hrefPrefix: element.href.slice(0, 30),
              hrefLength: element.href.length,
              rel: element.rel
            };
            return originalClick();
          };
        }
        return element;
      };
    }
    window.__isotopeOpenPathCalls = [];
    window.__isotopeOpenPathOverride = async (path) => {
      window.__isotopeOpenPathCalls.push({
        command: 'open_path',
        path: path ?? null
      });
      return { status: 'ok', path: path ?? '' };
    };
    return true;
  })()`;
}

function submitQuestionExpression(question) {
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

function clickButtonExpression(label) {
  return `(() => {
    const button = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.trim() === ${JSON.stringify(label)} || item.getAttribute('aria-label') === ${JSON.stringify(label)});
    if (!button) {
      throw new Error(${JSON.stringify(`button not found: ${label}`)});
    }
    button.click();
    return true;
  })()`;
}

function clickDialogButtonExpression(label) {
  return `(() => {
    const dialog = document.querySelector('[role="dialog"][aria-label="screen screenshot 原图"]');
    if (!dialog) {
      throw new Error('screen original dialog not found');
    }
    const button = [...dialog.querySelectorAll('button')]
      .find((item) => item.textContent?.trim() === ${JSON.stringify(label)});
    if (!button) {
      throw new Error(${JSON.stringify(`dialog button not found: ${label}`)});
    }
    button.click();
    return true;
  })()`;
}

function readBodyTextExpression() {
  return `(() => {
    const submitButton = [...document.querySelectorAll('button')]
      .find((item) => item.textContent?.trim() === '发送');
    return {
      text: document.body.innerText,
      buttons: [...document.querySelectorAll('button')].map((button) => ({
        text: button.textContent?.trim() ?? '',
        aria: button.getAttribute('aria-label')
      })),
      inputDisabled: document.querySelector('input')?.disabled ?? null,
      buttonDisabled: submitButton?.disabled ?? null
    };
  })()`;
}

function readScreenImageStateExpression() {
  return `(() => {
    const image = document.querySelector('img[alt="screen screenshot original"]');
    const title = document.querySelector('[role="dialog"][aria-label="screen screenshot 原图"] h2');
    return {
      artifactTitle: title?.textContent?.trim() ?? null,
      image: image ? {
        srcPrefix: image.getAttribute('src')?.slice(0, 30) ?? null,
        srcLength: image.getAttribute('src')?.length ?? 0,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight
      } : null
    };
  })()`;
}

function readScreenArtifactStateExpression() {
  return `(() => {
    const image = document.querySelector('img[alt="screen screenshot original"]');
    const dialog = document.querySelector('[role="dialog"][aria-label="screen screenshot 原图"]');
    const title = dialog?.querySelector('h2');
    const artifactPath = document.body.innerText
      ?.split(/\\r?\\n/)
      .map((line) => line.trim())
      .find((line) => line.includes(' · ') && line.endsWith('.json'))
      ?.split(' · ')
      .at(-1) ?? null;
    return {
      artifactTitle: title?.textContent?.trim() ?? null,
      image: image ? {
        srcPrefix: image.getAttribute('src')?.slice(0, 30) ?? null,
        srcLength: image.getAttribute('src')?.length ?? 0,
        naturalWidth: image.naturalWidth,
        naturalHeight: image.naturalHeight
      } : null,
      download: window.__isotopeDownloadInfo ?? null,
      folder: window.__isotopeOpenPathCalls?.at(-1) ?? window.__isotopeLastOpenPathResult ?? null,
      file: artifactPath ? {
        path: artifactPath,
        directory: artifactPath.replace(/[\\\\/][^\\\\/]+$/, '')
      } : null
    };
  })()`;
}

async function main() {
  const result = await runTauriScreenArtifactSmoke({
    cdpBaseUrl: process.env.ISOTOPE_TAURI_CDP_URL || 'http://127.0.0.1:9223',
    windowName: process.env.ISOTOPE_TAURI_CDP_WINDOW || 'main',
    question: process.env.ISOTOPE_TAURI_SCREEN_QUESTION || '观察屏幕并打开原图',
    timeoutMs: Number(process.env.ISOTOPE_TAURI_CDP_TIMEOUT_MS || 30000),
    minDataUrlLength: Number(process.env.ISOTOPE_TAURI_SCREEN_MIN_DATA_URL_LENGTH || DEFAULT_MIN_DATA_URL_LENGTH)
  });
  console.log(
    JSON.stringify(
      {
        status: 'ok',
        target: {
          url: result.target.url,
          title: result.target.title
        },
        artifactTitle: result.state.artifactTitle,
        image: result.state.image,
        download: result.state.download,
        folder: result.state.folder
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
