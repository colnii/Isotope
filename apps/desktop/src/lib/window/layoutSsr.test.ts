import { describe, expect, test } from 'vitest';
import { ssr } from '../../routes/+layout';

describe('desktop route rendering', () => {
  test('disables SSR so transparent Tauri windows do not paint the dev shell first', () => {
    expect(ssr).toBe(false);
  });
});
