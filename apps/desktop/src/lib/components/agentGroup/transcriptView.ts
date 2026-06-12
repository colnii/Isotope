import type {
  CodexTranscriptPage,
  TerminalTranscriptEvent,
  TranscriptEvent
} from '../../contracts/agentGroup';

export function readableTranscriptEvents(
  transcript: CodexTranscriptPage | null | undefined
): TerminalTranscriptEvent[] {
  if (!transcript) return [];
  if (transcript.terminal_events && transcript.terminal_events.length > 0) {
    return transcript.terminal_events;
  }
  return transcript.events
    .filter((event) => event.text.trim().length > 0)
    .map((event) => stripRawEvent(event));
}

export function formatTranscriptTimestamp(
  timestamp: string | null | undefined,
  timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
): string {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return timestamp;
  const values = Object.fromEntries(
    new Intl.DateTimeFormat('zh-CN', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    })
      .formatToParts(date)
      .map((part) => [part.type, part.value])
  );
  return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
}

function stripRawEvent(event: TranscriptEvent): TerminalTranscriptEvent {
  return {
    event_index: event.event_index,
    event_type: event.event_type,
    kind: event.kind,
    title: event.title,
    text: event.text,
    timestamp: event.timestamp,
    role: event.role
  };
}
