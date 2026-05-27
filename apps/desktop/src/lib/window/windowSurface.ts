export type DesktopWindowSurface = 'dev' | 'orb' | 'mini' | 'main';
export type ComponentSurface = 'dev' | 'window';

const tauriSurfaces = new Set<DesktopWindowSurface>(['orb', 'mini', 'main']);

export function resolveWindowSurface(search: string): DesktopWindowSurface {
  const value = new URLSearchParams(search).get('window') as DesktopWindowSurface | null;
  return value && tauriSurfaces.has(value) ? value : 'dev';
}

export function buildPageSurfaceClass(surface: DesktopWindowSurface): string {
  const base = 'min-h-screen text-isotope-text';
  return surface === 'dev' ? `${base} bg-isotope-bg p-6` : `${base} bg-transparent p-0`;
}

export function buildMiniWindowSurfaceClass(surface: ComponentSurface): string {
  const base = 'z-20 border border-isotope-line bg-white p-3 shadow-xl';
  return surface === 'dev'
    ? `${base} fixed bottom-28 right-5 w-[min(360px,calc(100vw-2.5rem))]`
    : `${base} min-h-screen w-screen overflow-auto`;
}
