import type { IsotopeSnapshot } from '../contracts/isotope';

export type MiniSubmitMode = 'real' | 'mock' | 'disabled';

export type MiniWindowView = {
  title: string;
  conversationLabel: string;
  submitMode: MiniSubmitMode;
  composerPlaceholder: string;
};

export function buildMiniWindowView(
  snapshot: IsotopeSnapshot,
  submitMode: MiniSubmitMode
): MiniWindowView {
  void snapshot;
  return {
    title: 'Isotope',
    conversationLabel: 'AI conversation',
    submitMode,
    composerPlaceholder: 'Ask Isotope'
  };
}
