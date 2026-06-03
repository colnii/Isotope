import { describe, expect, test } from 'vitest';
import { replayMockEvents } from '../client/replayMockEvents';
import { buildEventStreamView } from './eventStreamView';

describe('buildEventStreamView', () => {
  test('projects replay mock contract events without hiding their source', () => {
    const view = buildEventStreamView(replayMockEvents);

    expect(view.empty).toBe(false);
    expect(view.items.map((item) => [item.type, item.title, item.sourceKind])).toEqual([
      ['message_created', '用户请求桌面外壳', 'replay_mock'],
      ['worker_started', 'worker 会话已启动', 'replay_mock'],
      ['approval_required', '命令预览需要审批', 'replay_mock'],
      ['artifact_created', '产物摘要已创建', 'replay_mock'],
      ['error_reported', '工具预览失败', 'replay_mock']
    ]);
    expect(view.items[0]).toMatchObject({
      createdAt: '2026-05-27T00:00:01Z',
      summary: '用于静态 UI 验证的回放事件。'
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
      emptyMessage: '静态回放样例中暂无事件。',
      items: []
    });
  });
});
