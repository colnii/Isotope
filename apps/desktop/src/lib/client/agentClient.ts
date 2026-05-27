import type { IsotopeSnapshot } from '../contracts/isotope';
import { mockSnapshot } from './mockData';

export type AgentClient = {
  loadSnapshot(): Promise<IsotopeSnapshot>;
};

export function createAgentClient(baseUrl: string | null = null): AgentClient {
  const apiBaseUrl = normalizeBaseUrl(baseUrl);

  return {
    async loadSnapshot() {
      if (!apiBaseUrl) return mockSnapshot;

      try {
        const response = await fetch(`${apiBaseUrl}/desktop/snapshot`, { cache: 'no-store' });
        if (!response.ok) return mockSnapshot;
        return (await response.json()) as IsotopeSnapshot;
      } catch {
        return mockSnapshot;
      }
    }
  };
}

function normalizeBaseUrl(baseUrl: string | null): string | null {
  const trimmed = baseUrl?.trim();
  if (!trimmed) return null;
  return trimmed.replace(/\/$/, '');
}
