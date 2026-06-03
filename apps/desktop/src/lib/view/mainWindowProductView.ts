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
    chatEyebrow: 'AI 对话',
    workspaceTitle: 'Isotope',
    workspaceSubtitle: '',
    workspaceBody: '',
    emptyChatTitle: '问问 Isotope',
    emptyChatBody: '',
    composerPlaceholder: '问问 Isotope'
  };
}
