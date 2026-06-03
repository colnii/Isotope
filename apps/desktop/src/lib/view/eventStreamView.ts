import type { DataSourceInfo, IsotopeEvent } from '../contracts/isotope';

export type EventStreamItem = {
  id: string;
  type: IsotopeEvent['type'];
  title: string;
  createdAt: string;
  summary?: string;
  source: DataSourceInfo;
  sourceKind: DataSourceInfo['kind'];
};

export type EventStreamView = {
  empty: boolean;
  emptyMessage: string;
  items: EventStreamItem[];
};

export function buildEventStreamView(events: IsotopeEvent[]): EventStreamView {
  return {
    empty: events.length === 0,
    emptyMessage: '静态回放样例中暂无事件。',
    items: events.map((event) => ({
      id: event.id,
      type: event.type,
      title: event.title,
      createdAt: event.createdAt,
      summary: event.summary,
      source: event.source,
      sourceKind: event.source.kind
    }))
  };
}
