import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

function read(relativePath: string): string {
  return readFileSync(join(process.cwd(), relativePath), 'utf8');
}

describe('desktop Canvas Suprematist visual system', () => {
  test('defines the first-round design tokens', () => {
    const source = read('tailwind.config.ts');

    expect(source).toContain("canvas: '#f7f1e3'");
    expect(source).toContain("panel: '#fffcf4'");
    expect(source).toContain("'panel-raised': '#fff8ec'");
    expect(source).toContain("ink: '#202020'");
    expect(source).toContain("red: '#c9342c'");
    expect(source).toContain("blue: '#1d58a8'");
    expect(source).toContain("yellow: '#e2b631'");
    expect(source).toContain("line: '#d6cdbd'");
    expect(source).toContain("'line-strong': '#bdb4a4'");
  });

  test('registers shared main-chat component classes', () => {
    const source = read('src/app.css');

    expect(source).toContain('.iso-chat-shell');
    expect(source).toContain('.iso-chat-header');
    expect(source).toContain('.iso-chat-header-copy');
    expect(source).toContain('max-width: calc(100% - 11rem)');
    expect(source).toContain('.iso-suprematist-mark');
    expect(source).toContain('.iso-message-bubble-user');
    expect(source).toContain('.iso-capacity-card');
    expect(source).toContain('.iso-command-composer');
  });
});
