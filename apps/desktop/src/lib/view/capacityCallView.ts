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
    .map(([key, value]) => `${key}: ${formatInlineValue(value)}`);
  return [call.capacityId, ...resultParts].join(' · ');
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

function stringValue(value: unknown): string {
  return typeof value === 'string' && value.trim() ? value : '';
}
