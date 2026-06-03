<script lang="ts">
  let {
    placeholder = '给 Isotope 发消息',
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
  class="flex items-center gap-2 border border-isotope-line bg-white px-2 py-2 shadow-sm focus-within:border-isotope-running focus-within:ring-2 focus-within:ring-isotope-running/15"
  onsubmit={(event) => {
    event.preventDefault();
    submit();
  }}
>
  <input
    class="min-w-0 flex-1 bg-transparent px-2 py-1.5 text-sm outline-none placeholder:text-isotope-muted disabled:cursor-not-allowed"
    {placeholder}
    bind:value
    {disabled}
  />
  <button
    class="border border-isotope-running bg-isotope-running px-3 py-1.5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:border-isotope-line disabled:bg-isotope-panel disabled:text-isotope-muted"
    type="submit"
    {disabled}
  >
    发送
  </button>
</form>
