export type AgentGroupSummary = {
  group_id: string;
  title: string;
  goal: string;
  status: string;
};

export type ConnectedCodexMember = {
  member_id: string;
  group_id: string;
  display_name: string;
  member_kind: 'codex_session' | 'internal_agent' | 'supervisor';
  role: string;
  goal: string;
  send_policy: 'auto' | 'confirm' | 'draft_only';
  status:
    | 'active'
    | 'running'
    | 'idle'
    | 'needs_user'
    | 'terminated'
    | 'blocked'
    | 'archived';
  resume_session_id?: string | null;
  source_path?: string | null;
  managed_record_id?: string | null;
  transcript_policy?: Record<string, unknown>;
};

export type AgentGroupMessage = {
  message_id: string;
  group_id: string;
  from_member: string;
  to_member?: string | null;
  message_type: string;
  summary: string;
  payload?: Record<string, unknown>;
  created_at?: string;
};

export type PrivateChatMessage = {
  message_id: string;
  group_id: string;
  channel: 'private_human_chat';
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
};

export type AgentGroupDetail = {
  status: 'ok';
  group: AgentGroupSummary;
  connected_members: ConnectedCodexMember[];
  private_chat: PrivateChatMessage[];
  messages: AgentGroupMessage[];
  turns: unknown[];
};

export type TranscriptEvent = {
  event_index: number;
  kind: string;
  title: string;
  text: string;
  timestamp?: string | null;
  role?: string | null;
  raw?: unknown;
};

export type CodexTranscriptPage = {
  status: 'ok';
  session_id: string;
  source_path: string;
  source_size_bytes?: number;
  last_event_at?: string | null;
  offset: number;
  limit: number;
  latest?: boolean;
  next_offset: number;
  has_more: boolean;
  total_events: number;
  events: TranscriptEvent[];
};
