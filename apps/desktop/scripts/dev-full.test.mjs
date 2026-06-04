import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';
import { ensureDesktopEnvFile, resolveDesktopApiBaseUrl } from './dev-full.mjs';

describe('desktop full dev launcher env setup', () => {
  test('writes the default desktop API base URL when .env.local is missing', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'isotope-desktop-env-'));
    const envPath = join(directory, '.env.local');

    try {
      const result = await ensureDesktopEnvFile(envPath, {
        VITE_ISOTOPE_DESKTOP_API_BASE: undefined
      });

      await expect(readFile(envPath, 'utf8')).resolves.toBe(
        'VITE_ISOTOPE_DESKTOP_API_BASE=http://127.0.0.1:8765\n'
      );
      expect(result.apiBaseUrl).toBe('http://127.0.0.1:8765');
      expect(result.changed).toBe(true);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test('keeps an existing desktop API base URL instead of overwriting local env', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'isotope-desktop-env-'));
    const envPath = join(directory, '.env.local');
    const existing = 'OTHER=value\nVITE_ISOTOPE_DESKTOP_API_BASE=http://127.0.0.1:9999\n';

    try {
      await writeFile(envPath, existing, 'utf8');

      const result = await ensureDesktopEnvFile(envPath, {
        VITE_ISOTOPE_DESKTOP_API_BASE: 'http://127.0.0.1:8765'
      });

      await expect(readFile(envPath, 'utf8')).resolves.toBe(existing);
      expect(result.apiBaseUrl).toBe('http://127.0.0.1:9999');
      expect(result.changed).toBe(false);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test('uses the shell-provided API base URL when writing a new env file', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'isotope-desktop-env-'));
    const envPath = join(directory, '.env.local');

    try {
      const result = await ensureDesktopEnvFile(envPath, {
        VITE_ISOTOPE_DESKTOP_API_BASE: 'http://127.0.0.1:7777/'
      });

      await expect(readFile(envPath, 'utf8')).resolves.toBe(
        'VITE_ISOTOPE_DESKTOP_API_BASE=http://127.0.0.1:7777\n'
      );
      expect(result.apiBaseUrl).toBe('http://127.0.0.1:7777');
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });

  test('normalizes empty shell API base URL to the default', () => {
    expect(resolveDesktopApiBaseUrl({ VITE_ISOTOPE_DESKTOP_API_BASE: '  ' })).toBe('http://127.0.0.1:8765');
  });
});
