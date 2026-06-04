import { describe, expect, test } from 'vitest';
import type { DesktopCapacityCall } from '../client/agentClient';
import {
  capacityCallProductTitle,
  capacityCallStatusLabel,
  capacityCallSummary,
  capacityDetailLabel,
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
    expect(capacityCallSummary(call)).toBe('查询记忆 · 结果: 2');
    expect(capacityCallSummary({ ...call, resultSummary: {} })).toBe('查询记忆');
  });

  test('uses product titles for desktop actions', () => {
    expect(capacityCallProductTitle(call)).toBe('查询记忆');
    expect(
      capacityCallProductTitle({
        ...call,
        capacityId: 'supervisor.project_status',
        title: 'Supervisor Project Status'
      })
    ).toBe('查看项目态势');
    expect(
      capacityCallProductTitle({
        ...call,
        capacityId: 'isotope.self_repair',
        title: 'Isotope Self Repair'
      })
    ).toBe('启动 Isotope 自修复');
  });

  test('summarizes project status and self-repair actions in product language', () => {
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'supervisor.project_status',
        title: 'Supervisor Project Status',
        resultSummary: { agent_loop_project_status_status: 'completed' }
      })
    ).toBe('查看项目态势 · 状态: 已完成');
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'isotope.self_repair',
        title: 'Isotope Self Repair',
        resultSummary: {
          agent_loop_self_repair_status: 'launched',
          agent_loop_self_repair_managed_name: 'desktop-self-repair'
        }
      })
    ).toBe('启动 Isotope 自修复 · 状态: 已启动 · worker: desktop-self-repair');
  });

  test('localizes detail section labels', () => {
    expect(capacityDetailLabel('Inputs')).toBe('输入');
    expect(capacityDetailLabel('Result summary')).toBe('结果摘要');
    expect(capacityDetailLabel('Screen artifacts')).toBe('屏幕产物');
    expect(capacityDetailLabel('Custom')).toBe('Custom');
  });

  test('summarizes research search cards by report summary first', () => {
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'research.search',
        resultSummary: {
          agent_loop_executed: true,
          agent_loop_tick_status: 'executed',
          agent_loop_research_provider: 'codex_delegated',
          agent_loop_research_report_summary: 'Research report summary for desktop chat.',
          agent_loop_research_source_count: 1
        }
      })
    ).toBe(
      'research.search · Research report summary for desktop chat. · sources: 1 · provider: codex_delegated'
    );
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
