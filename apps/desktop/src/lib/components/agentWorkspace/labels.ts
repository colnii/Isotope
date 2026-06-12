export function workspaceChannelDisplayName(name: string): string {
  return name === 'general' ? '综合' : name;
}

export function workspaceDirectMessageTitle(title: string): string {
  return title === 'Coordinator AI' ? '协调 AI' : title;
}

export function workspaceMemberStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: '可用',
    running: '运行中',
    idle: '空闲',
    needs_user: '等待你处理',
    terminated: '已停止',
    blocked: '受阻',
    archived: '已移除'
  };
  return labels[status] ?? status;
}
