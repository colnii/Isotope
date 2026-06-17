#!/usr/bin/env node

import { access, appendFile, mkdir, readFile, writeFile } from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import { delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const DESKTOP_API_ENV_KEY = 'VITE_ISOTOPE_DESKTOP_API_BASE';
const DEFAULT_DESKTOP_API_BASE_URL = 'http://127.0.0.1:8765';

const scriptPath = fileURLToPath(import.meta.url);
const desktopDir = resolve(dirname(scriptPath), '..');
const repoRoot = resolve(desktopDir, '..', '..');

export function resolveDesktopApiBaseUrl(env = process.env) {
  const configured = env[DESKTOP_API_ENV_KEY]?.trim();
  return normalizeBaseUrl(configured || DEFAULT_DESKTOP_API_BASE_URL);
}

export async function ensureDesktopEnvFile(envPath, env = process.env) {
  const fallbackApiBaseUrl = resolveDesktopApiBaseUrl(env);
  const current = await readTextIfExists(envPath);
  const existingApiBaseUrl = readEnvValue(current, DESKTOP_API_ENV_KEY);

  if (existingApiBaseUrl) {
    return {
      apiBaseUrl: normalizeBaseUrl(existingApiBaseUrl),
      changed: false
    };
  }

  const nextLine = `${DESKTOP_API_ENV_KEY}=${fallbackApiBaseUrl}\n`;
  await mkdir(dirname(envPath), { recursive: true });
  if (current.length === 0) {
    await writeFile(envPath, nextLine, 'utf8');
  } else {
    const separator = current.endsWith('\n') ? '' : '\n';
    await appendFile(envPath, `${separator}${nextLine}`, 'utf8');
  }

  return {
    apiBaseUrl: fallbackApiBaseUrl,
    changed: true
  };
}

export function withRepoSourcePath(env = process.env, sourcePath = join(repoRoot, 'src')) {
  const currentPythonPath = env.PYTHONPATH?.trim();
  return {
    ...env,
    PYTHONPATH: currentPythonPath ? `${sourcePath}${delimiter}${currentPythonPath}` : sourcePath
  };
}

async function main() {
  const envPath = join(desktopDir, '.env.local');
  const envResult = await ensureDesktopEnvFile(envPath, process.env);
  const apiUrl = new URL(envResult.apiBaseUrl);
  const host = process.env.ISOTOPE_DESKTOP_BACKEND_HOST?.trim() || apiUrl.hostname;
  const port = Number(process.env.ISOTOPE_DESKTOP_BACKEND_PORT?.trim() || apiUrl.port || defaultPort(apiUrl));
  const frontendEnv = {
    ...process.env,
    [DESKTOP_API_ENV_KEY]: envResult.apiBaseUrl
  };
  const children = [];

  if (envResult.changed) {
    console.log(`Wrote ${DESKTOP_API_ENV_KEY} to ${relativeToDesktop(envPath)}: ${envResult.apiBaseUrl}`);
  } else {
    console.log(`Using ${DESKTOP_API_ENV_KEY} from ${relativeToDesktop(envPath)}: ${envResult.apiBaseUrl}`);
  }

  const backendRunning = await isBackendReady(envResult.apiBaseUrl);
  if (backendRunning) {
    console.log(`Reusing running Isotope backend at ${envResult.apiBaseUrl}`);
  } else {
    const backend = await spawnBackend({ host, port, env: process.env });
    children.push(backend);
    console.log(`Started Isotope backend at http://${host}:${port}`);
    await waitForBackend(envResult.apiBaseUrl);
  }

  const frontend = spawnChild(npmCommand(), ['run', 'dev'], {
    cwd: desktopDir,
    env: frontendEnv,
    name: 'desktop frontend'
  });
  children.push(frontend);

  await waitForChildren(children);
}

async function spawnBackend({ host, port, env }) {
  const command = env.ISOTOPE_SUPERVISOR_BIN?.trim() || supervisorCommand();
  await assertExecutable(command, 'Isotope supervisor');
  const backendEnv = withRepoSourcePath(env);
  return spawnChild(command, ['web', '--host', host, '--port', String(port)], {
    cwd: repoRoot,
    env: backendEnv,
    name: 'Isotope backend'
  });
}

function spawnChild(command, args, { cwd, env, name }) {
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: 'inherit',
    shell: false
  });

  child.once('error', (error) => {
    console.error(`${name} failed to start: ${error.message}`);
  });

  return child;
}

function waitForChildren(children) {
  let shuttingDown = false;

  const shutdown = (signal) => {
    if (shuttingDown) return;
    shuttingDown = true;
    for (const child of children) {
      if (!child.killed && child.exitCode === null) {
        child.kill(signal);
      }
    }
  };

  process.once('SIGINT', () => shutdown('SIGINT'));
  process.once('SIGTERM', () => shutdown('SIGTERM'));

  return new Promise((resolvePromise, reject) => {
    for (const child of children) {
      child.once('exit', (code, signal) => {
        shutdown(signal || 'SIGTERM');
        if (code && code !== 0) {
          reject(new Error(`child process exited with code ${code}`));
          return;
        }
        resolvePromise();
      });
    }
  });
}

async function isBackendReady(apiBaseUrl) {
  try {
    const response = await fetchWithTimeout(`${apiBaseUrl}/desktop/snapshot`, 750);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitForBackend(apiBaseUrl) {
  const timeoutMs = Number(process.env.ISOTOPE_DESKTOP_BACKEND_WAIT_MS || 10000);
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await isBackendReady(apiBaseUrl)) return;
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
  throw new Error(`Isotope backend did not become ready at ${apiBaseUrl} within ${timeoutMs}ms`);
}

async function fetchWithTimeout(url, timeoutMs) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      cache: 'no-store',
      signal: controller.signal
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function readTextIfExists(path) {
  try {
    return await readFile(path, 'utf8');
  } catch (error) {
    if (error?.code === 'ENOENT') return '';
    throw error;
  }
}

function readEnvValue(text, key) {
  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const pattern = new RegExp(`^\\s*(?:export\\s+)?${escapedKey}\\s*=\\s*(.*)\\s*$`, 'm');
  const match = text.match(pattern);
  if (!match) return null;
  return stripEnvQuotes(match[1]).trim() || null;
}

function stripEnvQuotes(value) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }
  return value;
}

function normalizeBaseUrl(url) {
  return url.trim().replace(/\/$/, '');
}

function supervisorCommand() {
  if (process.platform === 'win32') {
    return join(repoRoot, '.venv', 'Scripts', 'isotope-supervisor.exe');
  }
  return join(repoRoot, '.venv', 'bin', 'isotope-supervisor');
}

function npmCommand() {
  return process.platform === 'win32' ? 'npm.cmd' : 'npm';
}

async function assertExecutable(path, label) {
  try {
    await access(path, fsConstants.X_OK);
  } catch {
    throw new Error(`${label} command is not executable at ${path}. Run the repository Python setup first.`);
  }
}

function defaultPort(url) {
  return url.protocol === 'https:' ? '443' : '80';
}

function relativeToDesktop(path) {
  return path.startsWith(desktopDir) ? path.slice(desktopDir.length + 1) : path;
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
