import { createAgentClient } from './agentClient';
import { createAgentGroupClient } from './agentGroupClient';

export function resolveDesktopApiBaseUrl(): string | null {
  const configured = import.meta.env.VITE_ISOTOPE_DESKTOP_API_BASE as string | undefined;
  const trimmed = configured?.trim();
  return trimmed ? trimmed.replace(/\/$/, '') : null;
}

export function createIsotopeClient(baseUrl: string | null = resolveDesktopApiBaseUrl()) {
  const apiBaseUrl = baseUrl?.trim() ? baseUrl.trim().replace(/\/$/, '') : null;

  return {
    apiBaseUrl,
    hasRealApiBaseUrl: apiBaseUrl !== null,
    agentClient: createAgentClient(apiBaseUrl),
    agentGroupClient: createAgentGroupClient(apiBaseUrl)
  };
}

export type IsotopeClient = ReturnType<typeof createIsotopeClient>;
