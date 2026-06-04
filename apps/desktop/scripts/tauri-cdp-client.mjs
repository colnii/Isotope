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

export async function fetchTargets(cdpBaseUrl, fetchImpl) {
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

export function connectCdp(webSocketDebuggerUrl, WebSocketCtor) {
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
    close() {
      socket.close();
    }
  }));
}

export async function evaluate(session, expression) {
  const result = await session.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true
  });
  if (result.exceptionDetails) {
    throw new Error(`CDP Runtime.evaluate failed: ${JSON.stringify(result.exceptionDetails)}`);
  }
  return result.result?.value;
}

export async function connectTauriWebView({
  cdpBaseUrl = 'http://127.0.0.1:9223',
  windowName = 'main',
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
  await session.send('Runtime.enable');
  return { target, session };
}

export async function waitForState(session, readExpression, assertState, { timeoutMs = 10000, settleMs = 250 } = {}) {
  const startedAt = Date.now();
  let lastState = null;
  let lastError = null;
  while (Date.now() - startedAt <= timeoutMs) {
    if (settleMs > 0) {
      await new Promise((resolvePromise) => setTimeout(resolvePromise, settleMs));
    }
    lastState = await evaluate(session, readExpression);
    try {
      assertState(lastState);
      return lastState;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError ?? new Error(`CDP wait timed out after ${timeoutMs}ms`);
}
