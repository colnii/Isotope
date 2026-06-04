import type { DesktopCapacityCall, DesktopCapacityDetailSection } from '../client/agentClient';

export type ScreenCapacityArtifact = {
  artifactId: string;
  runId: string;
  summary: string;
};

export type ScreenArtifactAction = 'view-original' | 'open-folder' | 'download';

export function capacityCallStatusLabel(call: DesktopCapacityCall): string {
  switch (call.status) {
    case 'running':
      return '运行中';
    case 'ok':
      return '已完成';
    case 'blocked':
      return '受阻';
    case 'error':
      return '错误';
    default:
      return '未知';
  }
}

export function capacityCallProductTitle(call: DesktopCapacityCall): string {
  return ACTION_TITLES[call.capacityId] ?? call.title ?? call.capacityId;
}

export function capacityCallSummary(call: DesktopCapacityCall): string {
  if (call.capacityId === 'research.search') {
    const reportSummary = stringValue(call.resultSummary.agent_loop_research_report_summary);
    const sourceCount = call.resultSummary.agent_loop_research_source_count;
    const provider = stringValue(call.resultSummary.agent_loop_research_provider);
    const resultParts = [
      reportSummary,
      typeof sourceCount === 'number' ? `sources: ${sourceCount}` : '',
      provider ? `provider: ${provider}` : ''
    ].filter(Boolean);
    if (resultParts.length) {
      return [call.capacityId, ...resultParts].join(' · ');
    }
  }
  const resultParts = Object.entries(call.resultSummary)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .slice(0, 3)
    .map(([key, value]) => `${summaryFieldLabel(key)}: ${formatSummaryValue(key, value)}`);
  return [capacityCallProductTitle(call), ...resultParts].join(' · ');
}

export function capacityDetailLabel(label: string): string {
  return DETAIL_LABELS[label] ?? label;
}

export function formatCapacityDetailContent(section: DesktopCapacityDetailSection): string {
  if (section.kind === 'text') {
    return typeof section.content === 'string'
      ? section.content
      : formatInlineValue(section.content);
  }
  return JSON.stringify(section.content, null, 2);
}

export function screenArtifactsForCapacityCall(call: DesktopCapacityCall): ScreenCapacityArtifact[] {
  return call.details.flatMap((section) => {
    const content = section.content;
    if (!content || typeof content !== 'object' || Array.isArray(content)) return [];
    const artifacts = (content as Record<string, unknown>).artifacts;
    if (!Array.isArray(artifacts)) return [];
    return artifacts.flatMap((artifact) => {
      if (!artifact || typeof artifact !== 'object' || Array.isArray(artifact)) return [];
      const record = artifact as Record<string, unknown>;
      if (record.artifact_type !== 'screen_screenshot') return [];
      const ref = record.ref;
      const refRecord = ref && typeof ref === 'object' && !Array.isArray(ref) ? (ref as Record<string, unknown>) : {};
      const artifactId = stringValue(record.artifact_id) || stringValue(refRecord.artifact_id);
      const runId = stringValue(record.run_id) || stringValue(refRecord.run_id);
      if (!artifactId || !runId) return [];
      return [
        {
          artifactId,
          runId,
          summary: stringValue(record.summary) || 'screen screenshot'
        }
      ];
    });
  });
}

export function screenArtifactActions(): ScreenArtifactAction[] {
  return ['view-original', 'open-folder', 'download'];
}

function formatInlineValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return `${value.length} 项`;
  return JSON.stringify(value);
}

function summaryFieldLabel(key: string): string {
  return SUMMARY_FIELD_LABELS[key] ?? key;
}

function formatSummaryValue(key: string, value: unknown): string {
  if (key.endsWith('_status') && typeof value === 'string') {
    return ACTION_STATUS_VALUES[value] ?? value;
  }
  return formatInlineValue(value);
}

function stringValue(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '';
}

const ACTION_TITLES: Record<string, string> = {
  'memory.query': '查询记忆',
  'research.search': '检索资料',
  'research.promote': '沉淀资料',
  'screen.observe': '观察屏幕',
  'screen.report': '生成屏幕报告',
  'supervisor.project_status': '查看项目态势',
  'supervisor.request_context': '请求项目上下文',
  'supervisor.worker_review': '检查 worker',
  'supervisor.integration_review': '检查合入状态',
  'supervisor.codex_operation': '执行 Codex 操作',
  'coding_task.execute': '执行代码任务',
  'code.search': '搜索代码',
  'code.read': '读取代码',
  'code.apply_patch': '应用代码补丁',
  'test.run': '运行测试',
  'vcs.status': '查看代码状态',
  'vcs.diff': '查看代码差异',
  'workspace.materialize': '准备工作区',
  'workspace.isolated_rw': '创建隔离工作区',
  'workspace.release': '释放工作区',
  'artifact.review': '检查产物',
  'artifact.diff_summary': '生成变更摘要',
  'artifact.changed_files': '记录变更文件',
  'isotope.self_repair': '启动 Isotope 自修复'
};

const SUMMARY_FIELD_LABELS: Record<string, string> = {
  result_count: '结果',
  agent_loop_tick_status: '执行',
  agent_loop_project_status_status: '状态',
  agent_loop_self_repair_status: '状态',
  agent_loop_self_repair_managed_name: 'worker',
  agent_loop_self_repair_worker_role: '角色',
  agent_loop_self_repair_worktree_branch: '分支'
};

const ACTION_STATUS_VALUES: Record<string, string> = {
  executed: '已执行',
  completed: '已完成',
  launched: '已启动',
  ok: '已完成',
  blocked: '受阻',
  error: '错误'
};

const DETAIL_LABELS: Record<string, string> = {
  Inputs: '输入',
  'Result summary': '结果摘要',
  Results: '结果',
  'Screen artifacts': '屏幕产物'
};
