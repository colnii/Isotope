import type { IsotopeEvent } from '../contracts/isotope';

const replayMockSource = {
  kind: 'replay_mock',
  label: '静态回放样例',
  mockReason: '静态 EventStream 契约样例；尚未连接实时事件流。',
  expectedRealContract: 'GET desktop event replay and stream endpoints in a later task.'
} as const;

export const replayMockEvents = [
  {
    id: 'replay-event-message-1',
    eventCursor: 'replay-cursor-1',
    type: 'message_created',
    createdAt: '2026-05-27T00:00:01Z',
    source: replayMockSource,
    title: '用户请求桌面外壳',
    summary: '用于静态 UI 验证的回放事件。',
    payload: {
      messageId: 'message-1',
      role: 'user',
      preview: '构建桌面伴随窗口。'
    }
  },
  {
    id: 'replay-event-worker-1',
    eventCursor: 'replay-cursor-2',
    type: 'worker_started',
    createdAt: '2026-05-27T00:00:03Z',
    source: replayMockSource,
    title: 'worker 会话已启动',
    summary: '用于验证活动树相邻关系的静态 worker-started 事件。',
    payload: {
      workerId: 'worker-1',
      workerTitle: 'desktop-worker'
    }
  },
  {
    id: 'replay-event-approval-1',
    eventCursor: 'replay-cursor-3',
    type: 'approval_required',
    createdAt: '2026-05-27T00:00:05Z',
    source: replayMockSource,
    title: '命令预览需要审批',
    summary: '真实审批事件流接入前，此审批样例保持为 replay_mock。',
    payload: {
      approvalId: 'approval-1',
      riskLevel: 'medium',
      promptPreview: '是否批准预览命令？'
    }
  },
  {
    id: 'replay-event-artifact-1',
    eventCursor: 'replay-cursor-4',
    type: 'artifact_created',
    createdAt: '2026-05-27T00:00:07Z',
    source: replayMockSource,
    title: '产物摘要已创建',
    summary: '此静态外壳只展示低敏 ResourceRef。',
    payload: {
      artifactRef: {
        kind: 'artifact',
        id: 'artifact-1',
        label: 'desktop-design-summary'
      }
    }
  },
  {
    id: 'replay-event-error-1',
    eventCursor: 'replay-cursor-5',
    type: 'error_reported',
    createdAt: '2026-05-27T00:00:09Z',
    source: replayMockSource,
    title: '工具预览失败',
    summary: '用于验证错误渲染的静态错误样例。',
    payload: {
      errorCode: 'preview_failed',
      message: '仅用于预览的工具调用失败。'
    }
  }
] satisfies IsotopeEvent[];
