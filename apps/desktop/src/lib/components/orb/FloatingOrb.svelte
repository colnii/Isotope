<script lang="ts">
  import { windowDragClient } from '../../window/windowDragClient';

  let { surface = 'dev', onOpenMini = () => {} } = $props<{
    surface?: 'dev' | 'window';
    onOpenMini?: () => void;
  }>();

  const buttonTitle = $derived(surface === 'window' ? '打开 Isotope 对话' : '打开迷你窗口');
  const orbButtonClass = $derived(
    surface === 'window'
      ? 'relative grid h-16 w-16 cursor-move select-none place-items-center rounded-full border border-white/30 bg-teal-600 text-lg font-bold text-white outline-none'
      : 'relative grid h-16 w-16 place-items-center rounded-full border border-isotope-line bg-white text-sm font-semibold text-isotope-text shadow-lg transition hover:scale-[1.03] focus:outline-none focus:ring-2 focus:ring-inset focus:ring-isotope-running'
  );

  const dragThresholdPx = 4;
  let pointerIntent = $state<{
    pointerId: number;
    startX: number;
    startY: number;
    dragging: boolean;
  } | null>(null);

  function preventWindowContextMenu(event: MouseEvent) {
    if (surface !== 'window') return;
    event.preventDefault();
  }

  function handleOrbPointerDown(event: PointerEvent) {
    if (surface !== 'window' || event.button !== 0) return;
    event.preventDefault();
    pointerIntent = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      dragging: false
    };

    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.setPointerCapture(event.pointerId);
    }
  }

  function handleOrbPointerMove(event: PointerEvent) {
    if (surface !== 'window' || !pointerIntent || pointerIntent.pointerId !== event.pointerId) return;
    if (pointerIntent.dragging) return;

    const movedX = event.clientX - pointerIntent.startX;
    const movedY = event.clientY - pointerIntent.startY;
    if (Math.hypot(movedX, movedY) < dragThresholdPx) return;

    pointerIntent = { ...pointerIntent, dragging: true };
    void windowDragClient.startDragging();
  }

  function handleOrbPointerUp(event: PointerEvent) {
    if (surface !== 'window' || !pointerIntent || pointerIntent.pointerId !== event.pointerId) return;
    const shouldOpenMini = !pointerIntent.dragging;
    pointerIntent = null;

    if (event.currentTarget instanceof HTMLElement) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    if (shouldOpenMini) onOpenMini();
  }

  function handleOrbClick(event: MouseEvent) {
    if (surface === 'window') {
      event.preventDefault();
      return;
    }

    onOpenMini();
  }
</script>

<div
  class={surface === 'dev'
    ? 'fixed bottom-5 right-5 z-20 flex flex-col items-end gap-2'
    : 'grid h-screen w-screen place-items-center bg-transparent p-0'}
  aria-label="Isotope 悬浮球预览"
>
  <button
    type="button"
    class={orbButtonClass}
    aria-label="打开 Isotope 对话"
    title={buttonTitle}
    oncontextmenu={preventWindowContextMenu}
    onpointerdown={handleOrbPointerDown}
    onpointermove={handleOrbPointerMove}
    onpointerup={handleOrbPointerUp}
    onclick={handleOrbClick}
  >
    <span>{surface === 'window' ? 'I' : 'Iso'}</span>
  </button>
</div>
