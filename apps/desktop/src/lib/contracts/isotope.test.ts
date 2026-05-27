import { describe, expect, test } from 'vitest';
import {
  cursorForEvent,
  isLowSensitivePreview,
  sortActivityNodes,
  type ActivityNode,
  type IsotopeEvent
} from './isotope';

const realSource = { kind: 'real' as const, label: 'test', backendRef: 'test://source' };

describe('desktop contract helpers', () => {
  test('uses eventCursor before id for resumable event cursor', () => {
    const event: IsotopeEvent = {
      id: 'uuid-event-1',
      eventCursor: 'cursor-10',
      type: 'message_created',
      createdAt: '2026-05-27T00:00:00Z',
      source: realSource,
      title: 'Message',
      payload: { messageId: 'msg-1', role: 'assistant', preview: 'Done.' }
    };

    expect(cursorForEvent(event)).toBe('cursor-10');
  });

  test('falls back to id when eventCursor is absent', () => {
    const event: IsotopeEvent = {
      id: 'cursor-11',
      type: 'worker_started',
      createdAt: '2026-05-27T00:00:01Z',
      source: realSource,
      title: 'Worker started',
      payload: { workerId: 'worker-1', workerTitle: 'Review worker' }
    };

    expect(cursorForEvent(event)).toBe('cursor-11');
  });

  test('sorts activity nodes by parent, order, createdAt, then title/id', () => {
    const nodes: ActivityNode[] = [
      { id: 'b', kind: 'worker', title: 'B', status: 'running', source: realSource, parentId: 'root', createdAt: '2026-05-27T00:00:03Z' },
      { id: 'a', kind: 'worker', title: 'A', status: 'running', source: realSource, parentId: 'root', order: 1, createdAt: '2026-05-27T00:00:04Z' },
      { id: 'c', kind: 'worker', title: 'C', status: 'running', source: realSource, parentId: 'root', order: 0, createdAt: '2026-05-27T00:00:05Z' }
    ];

    expect(sortActivityNodes(nodes).map((node) => node.id)).toEqual(['c', 'a', 'b']);
  });

  test('rejects previews that expose obvious secrets or large content', () => {
    expect(isLowSensitivePreview('Short status summary.')).toBe(true);
    expect(isLowSensitivePreview('token=sk-test-secret')).toBe(false);
    expect(isLowSensitivePreview('x'.repeat(2200))).toBe(false);
  });
});
