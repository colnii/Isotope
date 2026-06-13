<script lang="ts">
  import type { ConnectedCodexMember } from '../../contracts/agentGroup';

  let { members, onStopMember, onOpenTranscript } = $props<{
    members: ConnectedCodexMember[];
    onStopMember: (memberId: string) => void;
    onOpenTranscript?: (member: ConnectedCodexMember) => void;
  }>();
</script>

<aside class="iso-agent-member-strip" aria-label="Connected AI sessions">
  <div class="flex gap-3 overflow-x-auto">
    {#each members as member (member.member_id)}
      <section class="iso-agent-panel min-w-64 px-3 py-2">
        <div class="flex items-start justify-between gap-3">
          <button
            class="min-w-0 flex-1 text-left"
            type="button"
            onclick={() => onOpenTranscript?.(member)}
          >
            <div class="truncate text-sm font-semibold text-isotope-text">{member.display_name}</div>
            <div class="mt-1 text-xs text-isotope-muted">
              {member.send_policy} / {member.status}
            </div>
            <div class="mt-1 line-clamp-2 text-xs leading-5 text-isotope-muted">{member.role}</div>
          </button>
          <button
            class="iso-agent-button-outline-danger shrink-0"
            type="button"
            disabled={member.status === 'terminated'}
            aria-label={`Stop ${member.display_name}`}
            onclick={() => onStopMember(member.member_id)}
          >
            Stop
          </button>
        </div>
      </section>
    {/each}
  </div>
</aside>
