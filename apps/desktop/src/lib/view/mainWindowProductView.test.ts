import { describe, expect, test } from 'vitest';
import { mockSnapshot } from '../client/mockData';
import { buildMainWindowProductView } from './mainWindowProductView';

describe('buildMainWindowProductView', () => {
  test('builds chat-only product copy without monitor sections', () => {
    const view = buildMainWindowProductView(mockSnapshot, mockSnapshot.activities[0]);

    expect('activityRailTitle' in view).toBe(false);
    expect('inspectorTitle' in view).toBe(false);
    expect('sourceKind' in view).toBe(false);
    expect(view.chatEyebrow).toBe('AI chat');
    expect(view.workspaceTitle).toBe('Isotope');
    expect(view.workspaceSubtitle).toBe('Capacity-aware assistant');
    expect(view.emptyChatTitle).toBe('Ask Isotope');
    expect(view.emptyChatBody).toBe('Capacity calls will appear inline when the assistant uses one.');
    expect(view.composerPlaceholder).toBe('Ask Isotope');
  });
});
