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
    workspaceSubtitle: '',
    workspaceBody: '',
    emptyChatTitle: 'Ask Isotope',
    emptyChatBody: '',
    composerPlaceholder: 'Ask Isotope'
  };
}
