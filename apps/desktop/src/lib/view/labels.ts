import type {
  ActivityNodeKind,
  ActivityStatus,
  ApprovalSummary,
  DataSourceKind
} from '../contracts/isotope';

export function activityKindLabel(kind: ActivityNodeKind | string): string {
  switch (kind) {
    case 'supervisor':
      return 'Supervisor';
    case 'worker':
      return 'worker';
    case 'agent':
      return 'Agent';
    case 'goal':
      return '目标';
    case 'capability_run':
      return 'capacity 调用';
    case 'tool_call':
      return '工具调用';
    case 'artifact':
      return '产物';
    case 'group':
      return '分组';
    default:
      return '未知';
  }
}

export function activityStatusLabel(status: ActivityStatus | string): string {
  switch (status) {
    case 'idle':
      return '空闲';
    case 'running':
      return '运行中';
    case 'needs_attention':
      return '需要处理';
    case 'done':
      return '已完成';
    case 'blocked':
      return '受阻';
    case 'error':
      return '错误';
    case 'unknown':
    default:
      return '未知';
  }
}

export function approvalStatusLabel(status: ApprovalSummary['status']): string {
  switch (status) {
    case 'pending':
      return '待处理';
    case 'resolved':
      return '已处理';
    case 'expired':
      return '已过期';
  }
}

export function approvalRiskLabel(riskLevel: ApprovalSummary['riskLevel']): string | undefined {
  switch (riskLevel) {
    case 'low':
      return '低风险';
    case 'medium':
      return '中风险';
    case 'high':
      return '高风险';
    default:
      return undefined;
  }
}

export function dataSourceKindLabel(kind: DataSourceKind | string): string {
  switch (kind) {
    case 'real':
      return '真实数据';
    case 'mock':
      return '模拟数据';
    case 'replay_mock':
      return '回放数据';
    case 'derived':
      return '派生数据';
    default:
      return '未知来源';
  }
}
