import { describe, expect, test } from 'vitest';
import type { DesktopCapacityCall } from '../client/agentClient';
import {
  capacityCallStatusLabel,
  capacityCallSummary,
  formatCapacityDetailContent
} from './capacityCallView';

const call: DesktopCapacityCall = {
  id: 'capacity_memory_query',
  capacityId: 'memory.query',
  title: 'Memory Query',
  status: 'ok',
  inputSummary: { query: 'capacity' },
  resultSummary: { result_count: 2 },
  details: [
    {
      label: 'Results',
      kind: 'json',
      content: { result_count: 2 }
    }
  ]
};

describe('capacityCallView', () => {
  test('labels capacity statuses for compact cards', () => {
    expect(capacityCallStatusLabel({ ...call, status: 'running' })).toBe('Running');
    expect(capacityCallStatusLabel({ ...call, status: 'ok' })).toBe('Done');
    expect(capacityCallStatusLabel({ ...call, status: 'blocked' })).toBe('Blocked');
    expect(capacityCallStatusLabel({ ...call, status: 'error' })).toBe('Error');
    expect(capacityCallStatusLabel({ ...call, status: 'unknown' })).toBe('Unknown');
  });

  test('summarizes capacity identity and result fields', () => {
    expect(capacityCallSummary(call)).toBe('memory.query · result_count: 2');
    expect(capacityCallSummary({ ...call, resultSummary: {} })).toBe('memory.query');
  });

  test('formats json and text details for scrollable display', () => {
    expect(
      formatCapacityDetailContent({
        label: 'Inputs',
        kind: 'json',
        content: { query: 'capacity' }
      })
    ).toContain('"query": "capacity"');
    expect(
      formatCapacityDetailContent({
        label: 'Note',
        kind: 'text',
        content: 'human text'
      })
    ).toBe('human text');
  });
});
