import { describe, expect, test } from 'vitest';
import type { DesktopCapacityCall } from '../client/agentClient';
import {
  capacityCallProductTitle,
  capacityCallStatusLabel,
  capacityCallSummary,
  capacityDetailLabel,
  formatCapacityDetailContent,
  researchRecallPreviewsForDetailSection,
  researchSourcePreviewsForDetailSection,
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
    expect(
      capacityCallProductTitle({
        ...call,
        capacityId: 'screen.control',
        title: 'Screen Control'
      })
    ).toBe('操作屏幕');
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
        capacityId: 'supervisor.project_status',
        title: 'Supervisor Project Status',
        resultSummary: {
          agent_loop_project_status_status: 'completed',
          agent_loop_project_status_open_capability_gap_count: 2
        }
      })
    ).toBe('查看项目态势 · 能力缺口: 2');
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'supervisor.project_status',
        title: 'Supervisor Project Status',
        resultSummary: {
          agent_loop_project_status_status: 'completed',
          agent_loop_project_status_self_repair_count: 1,
          agent_loop_project_status_latest_self_repair_name: 'desktop-self-repair',
          agent_loop_project_status_latest_self_repair_status: 'done',
          agent_loop_project_status_latest_self_repair_merge_suitable: true
        }
      })
    ).toBe('查看项目态势 · 最近自修复: desktop-self-repair / 已完成 / 可合并');
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
    expect(capacityDetailLabel('Result')).toBe('结果');
    expect(capacityDetailLabel('Result summary')).toBe('结果摘要');
    expect(capacityDetailLabel('Research artifacts')).toBe('研究产物');
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
          agent_loop_research_report: 'Research report summary for desktop chat.',
          agent_loop_research_source_count: 1
        }
      })
    ).toBe(
      'research.search · Research report summary for desktop chat. · sources: 1 · provider: codex_delegated'
    );
  });

  test('summarizes research search cards from result details when result summary is absent', () => {
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'research.search',
        resultSummary: {},
        details: [
          {
            label: 'Result',
            kind: 'json',
            content: {
              agent_loop_research_provider: 'tavily',
              agent_loop_research_report: 'Tavily returned 5 source-backed results.',
              agent_loop_research_source_count: 5
            }
          }
        ]
      })
    ).toBe('research.search · Tavily returned 5 source-backed results. · sources: 5 · provider: tavily');
  });

  test('summarizes research recall cards with retrieval status', () => {
    expect(
      capacityCallSummary({
        ...call,
        capacityId: 'research.recall',
        resultSummary: {
          agent_loop_research_recall_result_count: 1,
          agent_loop_research_recall_retrieval_backend: 'hybrid',
          agent_loop_research_recall_dense_status: 'ok'
        }
      })
    ).toBe('召回研究 · reports: 1 · hybrid/ok');
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

  test('extracts research source previews for product detail rendering', () => {
    const previews = researchSourcePreviewsForDetailSection({
      label: 'Result',
      kind: 'json',
      content: {
        agent_loop_research_source_previews: [
          {
            provider_rank: 2,
            source_id: 'src_002',
            title: 'OpenAI Developer Community',
            url: 'https://community.openai.com',
            snippet: 'June 4, 2026. Latest developer discussion.',
            why_used: 'Tavily search result rank 2, score 0.84'
          },
          {
            source_id: 'src_missing_url',
            title: 'No URL'
          }
        ]
      }
    });

    expect(previews).toEqual([
      {
        providerRank: 2,
        sourceId: 'src_002',
        title: 'OpenAI Developer Community',
        url: 'https://community.openai.com',
        snippet: 'June 4, 2026. Latest developer discussion.',
        whyUsed: 'Tavily search result rank 2, score 0.84'
      }
    ]);
  });

  test('extracts research recall previews for product detail rendering', () => {
    const previews = researchRecallPreviewsForDetailSection({
      label: 'Result',
      kind: 'json',
      content: {
        agent_loop_research_recall_previews: [
          {
            run_id: 'run_research',
            artifact_id: 'artifact_report',
            artifact_type: 'research.report',
            summary: 'Stored research report preview.',
            ref: {
              ref_type: 'artifact',
              scope: 'run',
              run_id: 'run_research',
              artifact_id: 'artifact_report'
            },
            source_refs: [{ ref_type: 'url', url: 'https://example.com' }],
            provenance: { execution_id: 'exec_research' }
          },
          {
            artifact_id: 'missing_run_id',
            summary: 'No run id.'
          }
        ]
      }
    });

    expect(previews).toEqual([
      {
        runId: 'run_research',
        artifactId: 'artifact_report',
        artifactType: 'research.report',
        summary: 'Stored research report preview.'
      }
    ]);
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
