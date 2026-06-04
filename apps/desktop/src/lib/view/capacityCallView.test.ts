import { describe, expect, test } from 'vitest';
import type { DesktopCapacityCall } from '../client/agentClient';
import {
  capacityCallStatusLabel,
  capacityCallSummary,
  formatCapacityDetailContent,
  screenArtifactsForCapacityCall,
  screenArtifactActions
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
    expect(capacityCallStatusLabel({ ...call, status: 'running' })).toBe('运行中');
    expect(capacityCallStatusLabel({ ...call, status: 'ok' })).toBe('已完成');
    expect(capacityCallStatusLabel({ ...call, status: 'blocked' })).toBe('受阻');
    expect(capacityCallStatusLabel({ ...call, status: 'error' })).toBe('错误');
    expect(capacityCallStatusLabel({ ...call, status: 'unknown' })).toBe('未知');
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

  test('extracts screen screenshot artifacts for original-image actions', () => {
    const screenCall: DesktopCapacityCall = {
      ...call,
      capacityId: 'screen.observe',
      details: [
        {
          label: 'Screen artifacts',
          kind: 'json',
          content: {
            artifacts: [
              {
                artifact_type: 'screen_metadata',
                artifact_id: 'artifact_metadata_001',
                run_id: 'run_screen_001',
                ref: {
                  ref_type: 'artifact',
                  scope: 'run',
                  run_id: 'run_screen_001',
                  artifact_id: 'artifact_metadata_001'
                }
              },
              {
                artifact_type: 'screen_screenshot',
                artifact_id: 'artifact_screen_001',
                run_id: 'run_screen_001',
                summary: 'screen screenshot captured',
                ref: {
                  ref_type: 'artifact',
                  scope: 'run',
                  run_id: 'run_screen_001',
                  artifact_id: 'artifact_screen_001'
                }
              }
            ]
          }
        }
      ]
    };

    const artifacts = screenArtifactsForCapacityCall(screenCall);

    expect(artifacts).toEqual([
      {
        artifactId: 'artifact_screen_001',
        runId: 'run_screen_001',
        summary: 'screen screenshot captured'
      }
    ]);
    expect(screenArtifactActions()).toEqual(['view-original', 'open-folder', 'download']);
  });
});
