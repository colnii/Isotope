import type { DesktopCapacityCall, DesktopCapacityDetailSection } from '../client/agentClient';

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

function formatInlineValue(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return `${value.length} 项`;
  return JSON.stringify(value);
}
