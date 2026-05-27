import { describe, expect, test } from 'vitest';
import type { ActivityNode } from '../../contracts/isotope';
import { buildActivityTreeRows } from './tree';

const source = { kind: 'real' as const, label: 'test', backendRef: 'test://activity' };

describe('buildActivityTreeRows', () => {
  test('projects parentId and childIds into stable indented rows', () => {
    const nodes: ActivityNode[] = [
      { id: 'worker-2', kind: 'worker', title: 'Worker B', status: 'running', source, parentId: 'root', order: 1 },
      { id: 'root', kind: 'supervisor', title: 'Supervisor', status: 'running', source, childIds: ['worker-1', 'worker-2'], order: 0 },
      { id: 'worker-1', kind: 'worker', title: 'Worker A', status: 'done', source, parentId: 'root', order: 0 }
    ];

    expect(buildActivityTreeRows(nodes, 'worker-2').map((row) => [row.node.id, row.depth, row.selected])).toEqual([
      ['root', 0, false],
      ['worker-1', 1, false],
      ['worker-2', 1, true]
    ]);
  });

  test('keeps orphan activities visible as root rows', () => {
    const nodes: ActivityNode[] = [
      { id: 'orphan', kind: 'goal', title: 'Orphan goal', status: 'running', source, parentId: 'missing' }
    ];

    expect(buildActivityTreeRows(nodes).map((row) => [row.node.id, row.depth])).toEqual([['orphan', 0]]);
  });
});
