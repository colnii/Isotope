import { describe, expect, it } from 'vitest';
import {
  formatTranscriptTimestamp,
  rawTranscriptPreviewText,
  readableTranscriptEvents
} from './transcriptView';
import type { CodexTranscriptPage } from '../../contracts/agentGroup';

describe('transcript terminal view helpers', () => {
  it('formats UTC transcript timestamps in the requested local timezone', () => {
    expect(formatTranscriptTimestamp('2026-06-11T20:40:39.602Z', 'Asia/Shanghai')).toBe(
      '2026-06-12 04:40:39'
    );
  });

  it('prefers terminal events and falls back to non-empty projected events', () => {
    const transcript = {
      status: 'ok',
      session_id: 'session_1',
      source_path: '/tmp/session.jsonl',
      offset: 0,
      limit: 1000,
      next_offset: 4,
      has_more: false,
      total_events: 4,
      events: [
        {
          event_index: 1,
          event_type: 'event_msg',
          kind: 'status',
          title: 'token_count',
          text: '',
          timestamp: '2026-06-11T20:40:39.602Z'
        },
        {
          event_index: 2,
          event_type: 'response_item',
          kind: 'message',
          title: 'assistant',
          text: 'fallback message',
          timestamp: '2026-06-11T20:40:40.602Z'
        }
      ],
      terminal_events: [
        {
          event_index: 3,
          event_type: 'response_item',
          kind: 'message',
          title: 'assistant',
          role: 'assistant',
          text: 'terminal message',
          timestamp: '2026-06-11T20:40:41.602Z'
        }
      ]
    } satisfies CodexTranscriptPage;

    expect(readableTranscriptEvents(transcript).map((event) => event.text)).toEqual([
      'terminal message'
    ]);
    expect(
      readableTranscriptEvents({ ...transcript, terminal_events: [] }).map((event) => event.text)
    ).toEqual(['fallback message']);
  });

  it('folds very large raw strings before rendering JSON previews', () => {
    const event = {
      event_index: 10,
      event_type: 'response_item',
      kind: 'raw_event',
      title: 'response_item',
      text: '',
      timestamp: '2026-06-11T20:40:39.602Z',
      raw: {
        type: 'response_item',
        payload: {
          type: 'reasoning',
          encrypted_content: 'x'.repeat(20_000),
          summary: []
        }
      }
    };

    const preview = rawTranscriptPreviewText(event);

    expect(preview.length).toBeLessThan(5_000);
    expect(preview).toContain('[已折叠 20000 字符]');
    expect(preview).not.toContain('x'.repeat(1_000));
  });
});
