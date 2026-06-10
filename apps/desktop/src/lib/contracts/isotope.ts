export type DataSourceKind = 'real' | 'mock' | 'replay_mock' | 'derived';

export type ResourceRef = {
  kind:
    | 'activity'
    | 'session'
    | 'agent'
    | 'goal'
    | 'event'
    | 'artifact'
    | 'approval'
    | 'tool_call'
    | 'capability_run';
  id: string;
  label?: string;
};

export type DataSourceInfo = {
  kind: DataSourceKind;
  label: string;
  backendRef?: string;
  sourceRef?: ResourceRef;
  replacementCondition?: string;
  mockReason?: string;
  expectedRealContract?: string;
};

export type ActivityNodeKind =
  | 'supervisor'
  | 'worker'
  | 'agent'
  | 'goal'
  | 'capability_run'
  | 'tool_call'
  | 'artifact'
  | 'group';

export type ActivityStatus =
  | 'idle'
  | 'running'
  | 'needs_attention'
  | 'done'
  | 'blocked'
  | 'error'
  | 'unknown';

export type ActivityNode = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  parentId?: string;
  childIds?: string[];
  relatedRefs?: ResourceRef[];
  sourceRef?: ResourceRef;
  order?: number;
  createdAt?: string;
  updatedAt?: string;
  summary?: string;
};

export type ActivitySummary = {
  id: string;
  kind: ActivityNodeKind;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
};

export type AgentSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  kind?: 'supervisor' | 'worker' | 'agent';
  role?: string;
  source: DataSourceInfo;
  updatedAt?: string;
};

export type GoalSummary = {
  id: string;
  title: string;
  status: ActivityStatus;
  source: DataSourceInfo;
  updatedAt?: string;
};

export type ApprovalSummary = {
  id: string;
  title: string;
  status: 'pending' | 'resolved' | 'expired';
  riskLevel?: 'low' | 'medium' | 'high';
  runId?: string;
  proposalId?: string;
  decisionId?: string;
  reasonCodes?: string[];
  requestedActionSummary?: Record<string, unknown>;
  source: DataSourceInfo;
};

export type DesktopReadResult = {
  scope: 'workspace' | 'local_file';
  status: string;
  path: string;
  excerpt?: string;
  truncated?: boolean;
  byte_count?: number;
  line_count?: number;
  content_policy?: string;
};

export type ArtifactSummary = {
  id: string;
  title: string;
  artifactRef: ResourceRef;
  source: DataSourceInfo;
};

export type ToolCallSummary = {
  id: string;
  toolName: string;
  status: 'running' | 'success' | 'failed' | 'cancelled' | 'unknown';
  source: DataSourceInfo;
};

export type SnapshotCounts = {
  runningAgents: number;
  needsAttention: number;
  approvals: number;
  artifacts: number;
  errors: number;
};

export type IsotopeSnapshot = {
  schemaVersion: 1;
  snapshotId: string;
  generatedAt: string;
  eventCursor?: string;
  lastEventId?: string;
  source: DataSourceInfo;
  activeActivity?: ActivitySummary;
  activeAgent?: AgentSummary;
  activeGoal?: GoalSummary;
  counts: SnapshotCounts;
  agents: AgentSummary[];
  activities: ActivityNode[];
  approvals: ApprovalSummary[];
  artifacts: ArtifactSummary[];
  runningToolCalls: ToolCallSummary[];
};

export type BaseEvent = {
  id: string;
  eventCursor?: string;
  createdAt: string;
  source: DataSourceInfo;
  activityId?: string;
  agentId?: string;
  parentEventId?: string;
  relatedRefs?: ResourceRef[];
  severity?: 'info' | 'success' | 'warning' | 'error';
  title: string;
  summary?: string;
  payloadPreview?: unknown;
};

export type IsotopeEvent =
  | (BaseEvent & {
      type: 'message_created';
      payload: { messageId: string; role: 'user' | 'assistant' | 'system' | 'tool'; preview: string };
    })
  | (BaseEvent & {
      type: 'worker_started';
      payload: { workerId: string; workerTitle: string };
    })
  | (BaseEvent & {
      type: 'worker_finished';
      payload: { workerId: string; result: 'done' | 'blocked' | 'failed' | 'cancelled' | 'unknown' };
    })
  | (BaseEvent & {
      type: 'tool_call_started';
      payload: { toolCallId: string; toolName: string };
    })
  | (BaseEvent & {
      type: 'tool_call_finished';
      payload: { toolCallId: string; toolName: string; result: 'success' | 'failed' | 'cancelled' | 'unknown' };
    })
  | (BaseEvent & {
      type: 'approval_required';
      payload: { approvalId: string; riskLevel?: 'low' | 'medium' | 'high'; promptPreview: string };
    })
  | (BaseEvent & {
      type: 'approval_resolved';
      payload: { approvalId: string; resolution: 'approved' | 'denied' | 'expired' | 'cancelled' };
    })
  | (BaseEvent & {
      type: 'artifact_created';
      payload: { artifactRef: ResourceRef };
    })
  | (BaseEvent & {
      type: 'error_reported';
      payload: { errorCode?: string; message: string };
    })
  | (BaseEvent & {
      type: 'snapshot_updated';
      payload: { snapshotId?: string; eventCursor?: string };
    });

export type EventReplayResponse = {
  events: IsotopeEvent[];
  nextCursor?: string;
  hasMore: boolean;
};

export function cursorForEvent(event: IsotopeEvent): string {
  return event.eventCursor ?? event.id;
}

export function sortActivityNodes(nodes: ActivityNode[]): ActivityNode[] {
  return [...nodes].sort((left, right) => {
    const parentCompare = (left.parentId ?? '').localeCompare(right.parentId ?? '');
    if (parentCompare !== 0) return parentCompare;

    const leftOrder = left.order ?? Number.POSITIVE_INFINITY;
    const rightOrder = right.order ?? Number.POSITIVE_INFINITY;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;

    const leftCreated = left.createdAt ?? '';
    const rightCreated = right.createdAt ?? '';
    if (leftCreated !== rightCreated) return leftCreated.localeCompare(rightCreated);

    const titleCompare = left.title.localeCompare(right.title);
    if (titleCompare !== 0) return titleCompare;

    return left.id.localeCompare(right.id);
  });
}

export function isLowSensitivePreview(value: string): boolean {
  const normalized = value.toLowerCase();
  if (value.length > 2000) return false;
  return !/(api[_-]?key|secret|token|sk-[a-z0-9_-]+)/i.test(normalized);
}
