import type { ActivityNode, IsotopeSnapshot } from '../contracts/isotope';

export type MainWindowProductView = {
  chatEyebrow: string;
  workspaceTitle: string;
  workspaceSubtitle: string;
  workspaceBody: string;
  emptyChatTitle: string;
  emptyChatBody: string;
  composerPlaceholder: string;
};

export function buildMainWindowProductView(
  snapshot: IsotopeSnapshot,
  selectedActivity: ActivityNode | null
): MainWindowProductView {
  void snapshot;
  void selectedActivity;

  return {
    chatEyebrow: 'AI chat',
    workspaceTitle: 'Isotope',
    workspaceSubtitle: 'Capacity-aware assistant',
    workspaceBody: 'Ask a question and review capacity calls inline when the assistant uses one.',
    emptyChatTitle: 'Ask Isotope',
    emptyChatBody: 'Capacity calls will appear inline when the assistant uses one.',
    composerPlaceholder: 'Ask Isotope'
  };
}
