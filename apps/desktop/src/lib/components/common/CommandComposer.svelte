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
  class="iso-command-composer"
  onsubmit={(event) => {
    event.preventDefault();
    submit();
  }}
>
  <input
    class="iso-command-input"
    {placeholder}
    bind:value
    {disabled}
  />
  <button
    class="iso-button-primary"
    type="submit"
    {disabled}
  >
    发送
  </button>
</form>
