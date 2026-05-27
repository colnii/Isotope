import type { IsotopeEvent } from '../contracts/isotope';

const replayMockSource = {
  kind: 'replay_mock',
  label: 'Static replay fixture',
  mockReason: 'Task 8R static EventStream contract shell; no live event stream is connected.',
  expectedRealContract: 'GET desktop event replay and stream endpoints in a later task.'
} as const;

export const replayMockEvents = [
  {
    id: 'replay-event-message-1',
    eventCursor: 'replay-cursor-1',
    type: 'message_created',
    createdAt: '2026-05-27T00:00:01Z',
    source: replayMockSource,
    title: 'User asked for the desktop shell',
    summary: 'Replay-only event fixture for static UI validation.',
    payload: {
      messageId: 'message-1',
      role: 'user',
      preview: 'Build the desktop companion shell.'
    }
  },
  {
    id: 'replay-event-worker-1',
    eventCursor: 'replay-cursor-2',
    type: 'worker_started',
    createdAt: '2026-05-27T00:00:03Z',
    source: replayMockSource,
    title: 'Worker session started',
    summary: 'Static worker-started event for ActivityTree adjacency.',
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
    title: 'Approval required for command preview',
    summary: 'Approval fixture remains replay_mock until a real approval stream exists.',
    payload: {
      approvalId: 'approval-1',
      riskLevel: 'medium',
      promptPreview: 'Approve the previewed command?'
    }
  },
  {
    id: 'replay-event-artifact-1',
    eventCursor: 'replay-cursor-4',
    type: 'artifact_created',
    createdAt: '2026-05-27T00:00:07Z',
    source: replayMockSource,
    title: 'Artifact summary created',
    summary: 'Only a low-sensitive ResourceRef is shown in this static shell.',
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
    title: 'Tool preview failed',
    summary: 'Static error fixture used to validate error rendering.',
    payload: {
      errorCode: 'preview_failed',
      message: 'A preview-only tool call failed.'
    }
  }
] satisfies IsotopeEvent[];
