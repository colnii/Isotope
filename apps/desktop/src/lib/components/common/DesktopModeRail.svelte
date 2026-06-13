<script lang="ts">
  export type DesktopMode = 'chat' | 'agent-workspace';

  let { mode, onModeChange } = $props<{
    mode: DesktopMode;
    onModeChange: (mode: DesktopMode) => void;
  }>();
</script>

<aside class="iso-desktop-mode-rail" aria-label="桌面模式切换">
  <div class="iso-desktop-mode-brand" aria-hidden="true">
    <span></span>
    <span></span>
    <span></span>
  </div>
  <nav class="iso-desktop-mode-nav" aria-label="主窗口模式">
    <button
      class={[
        'iso-desktop-mode-button',
        mode === 'chat' ? 'iso-desktop-mode-button-active' : ''
      ]}
      type="button"
      aria-pressed={mode === 'chat'}
      aria-label="主管聊天"
      title="主管聊天"
      onclick={() => onModeChange('chat')}
    >
      <span class="iso-desktop-mode-glyph" aria-hidden="true">聊</span>
      <span class="iso-desktop-mode-label">主管</span>
    </button>
    <button
      class={[
        'iso-desktop-mode-button',
        mode === 'agent-workspace' ? 'iso-desktop-mode-button-active' : ''
      ]}
      type="button"
      aria-pressed={mode === 'agent-workspace'}
      aria-label="智能体群聊"
      title="智能体群聊"
      onclick={() => onModeChange('agent-workspace')}
    >
      <span class="iso-desktop-mode-glyph" aria-hidden="true">群</span>
      <span class="iso-desktop-mode-label">群聊</span>
    </button>
  </nav>
</aside>
