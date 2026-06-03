import type { DataSourceInfo, IsotopeSnapshot } from '../contracts/isotope';
import { activityStatusLabel, dataSourceKindLabel } from './labels';

export type FloatingOrbView = {
  label: string;
  status: string;
  source: DataSourceInfo;
  needsAttention: number;
  attentionText: string | null;
  title: string;
};

export function buildFloatingOrbButtonTitle(surface: 'dev' | 'window', title: string): string | null {
  return surface === 'window' ? null : title;
}

export function buildFloatingOrbView(snapshot: IsotopeSnapshot): FloatingOrbView {
  const label = snapshot.activeActivity?.title ?? snapshot.activeAgent?.title ?? 'Isotope';
  const status = activityStatusLabel(snapshot.activeActivity?.status ?? snapshot.activeAgent?.status ?? 'idle');
  const needsAttention = snapshot.counts.needsAttention;

  return {
    label,
    status,
    source: snapshot.source,
    needsAttention,
    attentionText: needsAttention > 0 ? String(needsAttention) : null,
    title: `${label} / ${status} / ${dataSourceKindLabel(snapshot.source.kind)}`
  };
}
