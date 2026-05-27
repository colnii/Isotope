import { describe, expect, test } from 'vitest';
import { replayMockEvents } from '../client/replayMockEvents';
import { buildEventStreamView } from './eventStreamView';

describe('buildEventStreamView', () => {
  test('projects replay mock contract events without hiding their source', () => {
    const view = buildEventStreamView(replayMockEvents);

    expect(view.empty).toBe(false);
    expect(view.items.map((item) => [item.type, item.title, item.sourceKind])).toEqual([
      ['message_created', 'User asked for the desktop shell', 'replay_mock'],
      ['worker_started', 'Worker session started', 'replay_mock'],
      ['approval_required', 'Approval required for command preview', 'replay_mock'],
      ['artifact_created', 'Artifact summary created', 'replay_mock'],
      ['error_reported', 'Tool preview failed', 'replay_mock']
    ]);
    expect(view.items[0]).toMatchObject({
      createdAt: '2026-05-27T00:00:01Z',
      summary: 'Replay-only event fixture for static UI validation.'
    });
  });

  test('keeps every required event type in the fixture', () => {
    expect(new Set(replayMockEvents.map((event) => event.type))).toEqual(
      new Set(['message_created', 'worker_started', 'approval_required', 'artifact_created', 'error_reported'])
    );
  });

  test('reports an explicit empty state', () => {
    expect(buildEventStreamView([])).toEqual({
      empty: true,
      emptyMessage: 'No events in the static replay fixture.',
      items: []
    });
  });
});
