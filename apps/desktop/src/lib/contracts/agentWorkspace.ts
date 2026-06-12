export type WorkspaceStatus = 'active' | 'archived' | 'error';
export type WorkspaceConversationKind = 'channel' | 'dm';
export type WorkspaceSendPolicy = 'auto' | 'confirm' | 'draft_only';
export type WorkspaceMemberStatus =
  | 'active'
  | 'running'
  | 'idle'
  | 'needs_user'
  | 'terminated'
  | 'blocked'
  | 'archived';

export type AgentWorkspaceSummary = {
  workspace_id: string;
  title: string;
  root_path: string;
  status: WorkspaceStatus;
  created_at: string;
  updated_at: string;
};

export type AgentWorkspaceChannel = {
  channel_id: string;
  workspace_id: string;
  name: string;
  topic: string;
  status: WorkspaceStatus;
  created_at: string;
  updated_at: string;
};

export type AgentWorkspaceDirectMessage = {
  dm_id: string;
  workspace_id: string;
  dm_kind: 'coordinator' | 'codex_member';
  title: string;
  target_member_id: string | null;
  status: WorkspaceStatus;
  created_at: string;
  updated_at: string;
};

export type AgentWorkspaceMember = {
  member_id: string;
  workspace_id: string;
  channel_id: string;
  display_name: string;
  member_kind: 'codex_session' | 'internal_agent' | 'supervisor';
  role: string;
  goal: string;
  send_policy: WorkspaceSendPolicy;
  status: WorkspaceMemberStatus;
  resume_session_id: string | null;
  source_path: string | null;
  managed_record_id: string | null;
  transcript_policy: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type WorkspaceConversationMessage = {
  message_id: string;
  workspace_id: string;
  conversation_type: WorkspaceConversationKind;
  conversation_id: string;
  from_actor: string;
  to_actor: string | null;
  message_type: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type WorkspaceRuntimeControlRecord = {
  control_id: string;
  workspace_id: string;
  conversation_type: WorkspaceConversationKind;
  conversation_id: string;
  intent: 'queue' | 'interrupt' | 'terminate';
  target: 'current_run' | 'member';
  target_member_id: string | null;
  reason: string;
  created_at: string;
};

export type WorkspaceControlEvent = {
  event_id: string;
  workspace_id: string;
  conversation_type: WorkspaceConversationKind;
  conversation_id: string;
  event_type: 'runtime_control';
  payload: WorkspaceRuntimeControlRecord;
  created_at: string;
};

export type AgentWorkspaceListPayload = {
  status: 'ok';
  workspaces: AgentWorkspaceSummary[];
};

export type AgentWorkspaceDetail = {
  status: 'ok';
  workspace: AgentWorkspaceSummary;
  channels: AgentWorkspaceChannel[];
  direct_messages: AgentWorkspaceDirectMessage[];
  members: AgentWorkspaceMember[];
  messages: WorkspaceConversationMessage[];
  controls: WorkspaceControlEvent[];
};

export type CodexSessionCandidate = {
  session_id: string;
  short_session_id: string;
  title: string;
  cwd: string | null;
  source_path: string;
  source_size_bytes: number;
  last_event_at: string | null;
  preview: string;
};

export type CodexSessionCandidatePayload = {
  status: 'ok';
  scope: 'cwd' | 'all';
  sessions: CodexSessionCandidate[];
};

export type CreateWorkspaceChannelRequest = {
  name: string;
  topic?: string;
};

export type UpdateWorkspaceRequest = {
  title: string;
  root_path: string;
};

export type AddWorkspaceMemberRequest = {
  display_name: string;
  role: string;
  goal: string;
  send_policy: WorkspaceSendPolicy;
  resume_session_id: string | null;
  source_path: string | null;
  managed_record_id: string | null;
};

export type UpdateWorkspaceMemberRequest = {
  send_policy?: WorkspaceSendPolicy;
  status?: WorkspaceMemberStatus;
  role?: string;
  goal?: string;
};
