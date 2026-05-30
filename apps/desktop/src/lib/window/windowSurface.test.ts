import { describe, expect, test } from 'vitest';
import {
  buildMiniWindowSurfaceClass,
  buildPageSurfaceClass,
  resolveWindowSurface
} from './windowSurface';

describe('resolveWindowSurface', () => {
  test.each([
    ['?window=orb', 'orb'],
    ['?window=mini', 'mini'],
    ['?window=main', 'main'],
    ['', 'dev'],
    ['?window=unknown', 'dev']
  ] as const)('maps %s to %s', (search, expected) => {
    expect(resolveWindowSurface(search)).toBe(expected);
  });
});

describe('buildPageSurfaceClass', () => {
  test('keeps the browser dev shell padded and opaque', () => {
    expect(buildPageSurfaceClass('dev')).toContain('p-6');
    expect(buildPageSurfaceClass('dev')).toContain('bg-isotope-bg');
  });

  test('uses transparent unpadded layout for Tauri window surfaces', () => {
    expect(buildPageSurfaceClass('mini')).toContain('p-0');
    expect(buildPageSurfaceClass('mini')).toContain('bg-transparent');
  });

  test('hides overflow in compact floating window surfaces', () => {
    expect(buildPageSurfaceClass('orb')).toContain('overflow-hidden');
    expect(buildPageSurfaceClass('mini')).toContain('overflow-hidden');
    expect(buildPageSurfaceClass('main')).not.toContain('overflow-hidden');
  });
});

describe('buildMiniWindowSurfaceClass', () => {
  test('keeps dev MiniWindow as a fixed preview', () => {
    expect(buildMiniWindowSurfaceClass('dev')).toContain('fixed');
    expect(buildMiniWindowSurfaceClass('dev')).toContain('bottom-28');
  });

  test('uses document-flow layout inside the independent MiniWindow', () => {
    expect(buildMiniWindowSurfaceClass('window')).toContain('h-screen');
    expect(buildMiniWindowSurfaceClass('window')).toContain('w-screen');
    expect(buildMiniWindowSurfaceClass('window')).toContain('box-border');
    expect(buildMiniWindowSurfaceClass('window')).toContain('overflow-hidden');
    expect(buildMiniWindowSurfaceClass('window')).not.toContain('overflow-auto');
    expect(buildMiniWindowSurfaceClass('window')).not.toContain('fixed');
  });
});
