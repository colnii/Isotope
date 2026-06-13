import type { DesktopCapacityCall, DesktopCapacityDetailSection } from '../client/agentClient';

export type ScreenCapacityArtifact = {
  artifactId: string;
  runId: string;
  summary: string;
};

export type ResearchSourcePreview = {
  providerRank?: number;
  sourceId: string;
  title: string;
  url: string;
  snippet: string;
  whyUsed: string;
};

export type ResearchRecallPreview = {
  runId: string;
  artifactId: string;
  artifactType: string;
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
    const resultRecord = resultRecordForCapacityCall(call);
    const reportSummary =
      stringValue(resultRecord.agent_loop_research_report) ||
      stringValue(resultRecord.agent_loop_research_report_summary);
    const sourceCount = resultRecord.agent_loop_research_source_count;
    const provider = stringValue(resultRecord.agent_loop_research_provider);
    const resultParts = [
      reportSummary,
      typeof sourceCount === 'number' ? `sources: ${sourceCount}` : '',
      provider ? `provider: ${provider}` : ''
    ].filter(Boolean);
    if (resultParts.length) {
      return [call.capacityId, ...resultParts].join(' · ');
    }
  }
  if (call.capacityId === 'research.recall') {
    const resultRecord = resultRecordForCapacityCall(call);
    const resultCount = resultRecord.agent_loop_research_recall_result_count;
    const backend = stringValue(resultRecord.agent_loop_research_recall_retrieval_backend);
    const denseStatus = stringValue(resultRecord.agent_loop_research_recall_dense_status);
    const retrieval = [backend, denseStatus].filter(Boolean).join('/');
    const resultParts = [
      typeof resultCount === 'number' ? `reports: ${resultCount}` : '',
      retrieval
    ].filter(Boolean);
    if (resultParts.length) {
      return [capacityCallProductTitle(call), ...resultParts].join(' · ');
    }
  }
  if (call.capacityId === 'supervisor.project_status') {
    const latestSelfRepair = projectStatusLatestSelfRepairSummary(call.resultSummary);
    if (latestSelfRepair) {
      return [capacityCallProductTitle(call), latestSelfRepair].join(' · ');
    }
    const openGaps = projectStatusCapabilityGapSummary(call.resultSummary);
    if (openGaps) {
      return [capacityCallProductTitle(call), openGaps].join(' · ');
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

export function researchSourcePreviewsForDetailSection(
  section: DesktopCapacityDetailSection
): ResearchSourcePreview[] {
  if (!isRecord(section.content)) return [];
  const previews = section.content.agent_loop_research_source_previews;
  if (!Array.isArray(previews)) return [];
  return previews.flatMap((preview) => {
    if (!isRecord(preview)) return [];
    const title = stringValue(preview.title);
    const url = stringValue(preview.url);
    if (!title || !url) return [];
    const providerRank = preview.provider_rank;
    return [
      {
        providerRank: typeof providerRank === 'number' ? providerRank : undefined,
        sourceId: stringValue(preview.source_id),
        title,
        url,
        snippet: stringValue(preview.snippet),
        whyUsed: stringValue(preview.why_used)
      }
    ];
  });
}

export function researchRecallPreviewsForDetailSection(
  section: DesktopCapacityDetailSection
): ResearchRecallPreview[] {
  if (!isRecord(section.content)) return [];
  const previews = section.content.agent_loop_research_recall_previews;
  if (!Array.isArray(previews)) return [];
  return previews.flatMap((preview) => {
    if (!isRecord(preview)) return [];
    const runId = stringValue(preview.run_id);
    const artifactId = stringValue(preview.artifact_id);
    const summary = stringValue(preview.summary);
    if (!runId || !artifactId || !summary) return [];
    return [
      {
        runId,
        artifactId,
        artifactType: stringValue(preview.artifact_type) || 'research.report',
        summary
      }
    ];
  });
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

function resultRecordForCapacityCall(call: DesktopCapacityCall): Record<string, unknown> {
  if (Object.keys(call.resultSummary).length > 0) {
    return call.resultSummary;
  }
  const resultSection = call.details.find(
    (section) =>
      ['Result', 'Results', 'Result summary', '结果', '结果摘要'].includes(section.label) &&
      isRecord(section.content)
  );
  return resultSection && isRecord(resultSection.content) ? resultSection.content : {};
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
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

function projectStatusLatestSelfRepairSummary(resultSummary: Record<string, unknown>): string {
  const name = stringValue(
    resultSummary.agent_loop_project_status_latest_self_repair_name
  );
  if (!name) return '';
  const status = stringValue(
    resultSummary.agent_loop_project_status_latest_self_repair_status
  );
  const statusLabel = status ? (ACTION_STATUS_VALUES[status] ?? status) : '状态未知';
  const mergeSuitable =
    resultSummary.agent_loop_project_status_latest_self_repair_merge_suitable;
  const mergeLabel = mergeSuitable === true ? '可合并' : '需复查';
  return `最近自修复: ${name} / ${statusLabel} / ${mergeLabel}`;
}

function projectStatusCapabilityGapSummary(resultSummary: Record<string, unknown>): string {
  const count = resultSummary.agent_loop_project_status_open_capability_gap_count;
  if (typeof count !== 'number' || count <= 0) return '';
  return `能力缺口: ${count}`;
}

function stringValue(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '';
}

const ACTION_TITLES: Record<string, string> = {
  'memory.query': '查询记忆',
  'research.recall': '召回研究',
  'research.search': '检索资料',
  'research.promote': '沉淀资料',
  'screen.observe': '观察屏幕',
  'screen.control': '操作屏幕',
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
  done: '已完成',
  working: '进行中',
  needs_user: '需确认',
  ok: '已完成',
  blocked: '受阻',
  error: '错误'
};

const DETAIL_LABELS: Record<string, string> = {
  Inputs: '输入',
  Result: '结果',
  'Result summary': '结果摘要',
  Results: '结果',
  'Research artifacts': '研究产物',
  'Screen artifacts': '屏幕产物'
};
