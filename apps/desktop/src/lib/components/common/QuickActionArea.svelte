<script lang="ts">
  const actions = ['/ commands', 'Context', 'Attention', 'Artifacts'];
</script>

<div class="grid grid-cols-2 gap-2 text-xs">
  {#each actions as action}
    <button class="border border-isotope-line px-2 py-1 text-left text-isotope-muted" type="button">
      {action}
    </button>
  {/each}
</div>
