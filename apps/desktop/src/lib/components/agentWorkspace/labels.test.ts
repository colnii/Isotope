import { describe, expect, test } from 'vitest';
import {
  workspaceChannelDisplayName,
  workspaceDirectMessageTitle,
  workspaceMemberStatusLabel
} from './labels';

describe('Agent Workspace Chinese labels', () => {
  test('localizes built-in workspace conversation names', () => {
    expect(workspaceChannelDisplayName('general')).toBe('综合');
    expect(workspaceDirectMessageTitle('Coordinator AI')).toBe('协调 AI');
  });

  test('localizes member statuses without changing unknown values', () => {
    expect(workspaceMemberStatusLabel('running')).toBe('运行中');
    expect(workspaceMemberStatusLabel('needs_user')).toBe('等待你处理');
    expect(workspaceMemberStatusLabel('custom_state')).toBe('custom_state');
  });
});
