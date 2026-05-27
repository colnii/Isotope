<script lang="ts">
  let {
    placeholder = 'Message Isotope',
    disabled = false,
    onSubmit
  } = $props<{
    placeholder?: string;
    disabled?: boolean;
    onSubmit: (value: string) => void;
  }>();

  let value = $state('');

  function submit() {
    const text = value.trim();
    if (!text || disabled) return;
    onSubmit(text);
    value = '';
  }
</script>

<form
  class="flex gap-2"
  onsubmit={(event) => {
    event.preventDefault();
    submit();
  }}
>
  <input
    class="min-w-0 flex-1 border border-isotope-line px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-isotope-running"
    {placeholder}
    bind:value
    {disabled}
  />
  <button class="bg-isotope-running px-3 py-2 text-sm text-white disabled:opacity-50" type="submit" {disabled}>
    Send
  </button>
</form>
