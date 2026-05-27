import { sortActivityNodes, type ActivityNode } from '../../contracts/isotope';

export type ActivityTreeRow = {
  node: ActivityNode;
  depth: number;
  selected: boolean;
};

export function buildActivityTreeRows(
  nodes: ActivityNode[],
  selectedId: string | null = null
): ActivityTreeRow[] {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const childrenByParent = new Map<string, ActivityNode[]>();

  for (const node of nodes) {
    if (!node.parentId || !byId.has(node.parentId)) continue;
    const children = childrenByParent.get(node.parentId) ?? [];
    children.push(node);
    childrenByParent.set(node.parentId, children);
  }

  const childIds = new Set(nodes.flatMap((node) => node.childIds ?? []));
  const roots = sortActivityNodes(
    nodes.filter((node) => (!node.parentId || !byId.has(node.parentId)) && !childIds.has(node.id))
  );
  const rows: ActivityTreeRow[] = [];
  const visited = new Set<string>();

  function visit(node: ActivityNode, depth: number) {
    if (visited.has(node.id)) return;
    visited.add(node.id);
    rows.push({ node, depth, selected: selectedId === node.id });

    const explicitChildren = (node.childIds ?? [])
      .map((id) => byId.get(id))
      .filter((child): child is ActivityNode => Boolean(child));
    const parentChildren = childrenByParent.get(node.id) ?? [];
    const childMap = new Map([...explicitChildren, ...parentChildren].map((child) => [child.id, child]));

    for (const child of sortActivityNodes([...childMap.values()])) {
      visit(child, depth + 1);
    }
  }

  for (const root of roots) visit(root, 0);
  for (const node of sortActivityNodes(nodes)) visit(node, 0);
  return rows;
}
