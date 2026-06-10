#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptPath = fileURLToPath(import.meta.url);
const scriptDir = dirname(scriptPath);
const desktopDir = resolve(scriptDir, '..');

const OBSERVE_MODES = Object.freeze({
  cdp: {
    script: 'tauri-cdp-smoke.mjs',
    summary: 'Drive the main Tauri WebView through CDP and capture DOM state.'
  },
  screen: {
    script: 'tauri-screen-artifact-smoke.mjs',
    summary: 'Drive screen.observe and verify screenshot artifact actions.'
  }
});

export function parseObserveArgs(argv = [], env = process.env) {
  let mode = env.ISOTOPE_DESKTOP_OBSERVE_MODE?.trim() || 'cdp';
  let plan = false;

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--plan') {
      plan = true;
    } else if (arg === '--cdp') {
      mode = 'cdp';
    } else if (arg === '--screen') {
      mode = 'screen';
    } else if (arg === '--mode') {
      index += 1;
      mode = argv[index] ?? '';
    } else if (arg.startsWith('--mode=')) {
      mode = arg.slice('--mode='.length);
    } else if (arg === '--help' || arg === '-h') {
      plan = true;
    } else {
      throw new Error(`unsupported desktop observe argument: ${arg}`);
    }
  }

  assertObserveMode(mode);
  return { mode, plan };
}

export function buildObserveCommand(
  mode,
  { nodeCommand = process.execPath, scriptDir: selectedScriptDir = scriptDir } = {}
) {
  assertObserveMode(mode);
  const config = OBSERVE_MODES[mode];
  return {
    mode,
    summary: config.summary,
    argv: [nodeCommand, join(selectedScriptDir, config.script)]
  };
}

export function buildObservePlan(options = {}) {
  const modes = Object.fromEntries(
    Object.keys(OBSERVE_MODES).map((mode) => {
      const command = buildObserveCommand(mode, options);
      return [
        mode,
        {
          summary: command.summary,
          command: command.argv
        }
      ];
    })
  );

  return {
    defaultMode: 'cdp',
    setup: [
      'npm run dev:full',
      'start Tauri with WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9223 --remote-allow-origins=*"',
      'use Windows Node directly when running from a WSL checkout'
    ],
    modes,
    environment: {
      ISOTOPE_DESKTOP_OBSERVE_MODE: 'cdp | screen',
      ISOTOPE_TAURI_CDP_URL: 'defaults to http://127.0.0.1:9223'
    }
  };
}

export async function runDesktopObserve({
  argv = process.argv.slice(2),
  env = process.env,
  spawnImpl = spawn,
  stdout = process.stdout,
  stderr = process.stderr
} = {}) {
  const parsed = parseObserveArgs(argv, env);
  if (parsed.plan) {
    stdout.write(`${JSON.stringify(buildObservePlan(), null, 2)}\n`);
    return 0;
  }

  const command = buildObserveCommand(parsed.mode);
  stdout.write(
    `${JSON.stringify(
      {
        status: 'running',
        mode: command.mode,
        summary: command.summary,
        command: command.argv
      },
      null,
      2
    )}\n`
  );

  return new Promise((resolvePromise) => {
    const child = spawnImpl(command.argv[0], command.argv.slice(1), {
      cwd: desktopDir,
      env,
      stdio: 'inherit',
      shell: false
    });

    child.once('error', (error) => {
      stderr.write(`desktop observe failed to start: ${error.message}\n`);
      stderr.write(`${observeFailureGuidance(command.mode)}\n`);
      resolvePromise(1);
    });

    child.once('exit', (code, signal) => {
      if (code === 0) {
        resolvePromise(0);
        return;
      }
      stderr.write(`desktop observe ${command.mode} exited with ${signal || code}.\n`);
      stderr.write(`${observeFailureGuidance(command.mode)}\n`);
      resolvePromise(code ?? 1);
    });
  });
}

export function observeFailureGuidance(mode) {
  assertObserveMode(mode);
  return [
    'Before rerunning, keep the desktop backend/frontend alive with npm run dev:full.',
    'Start the Tauri app with WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9223 --remote-allow-origins=*".',
    mode === 'screen'
      ? 'Screen mode also needs a backend path that can complete screen.observe and return a screenshot artifact.'
      : 'Use --mode screen only when the task needs screenshot artifact verification.'
  ].join('\n');
}

function assertObserveMode(mode) {
  if (!Object.hasOwn(OBSERVE_MODES, mode)) {
    throw new Error(`desktop observe mode must be one of: ${Object.keys(OBSERVE_MODES).join(', ')}`);
  }
}

if (process.argv[1] && resolve(process.argv[1]) === scriptPath) {
  runDesktopObserve().then((code) => {
    process.exitCode = code;
  }).catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
}
