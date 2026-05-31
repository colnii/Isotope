import { describe, expect, test } from 'vitest';
import { mockSnapshot } from '../client/mockData';
import { buildMainWindowProductView } from './mainWindowProductView';

describe('buildMainWindowProductView', () => {
  test('builds quiet product shell sections from the desktop snapshot', () => {
    const view = buildMainWindowProductView(mockSnapshot, mockSnapshot.activities[0]);

    expect(view.activityRailTitle).toBe('Activities');
    expect(view.workspaceTitle).toBe('Connect the desktop MVP');
    expect(view.workspaceSubtitle).toBe('Mock Supervisor');
    expect(view.inspectorTitle).toBe('Inspector');
    expect(view.sourceKind).toBe('mock');
    expect(view.chatEyebrow).toBe('Supervisor chat');
    expect(view.emptyChatTitle).toBe('Ask Isotope about this workspace');
    expect(view.composerPlaceholder).toBe('Ask Isotope about this run');
  });
});
