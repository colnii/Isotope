"""Panel CSS for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_STYLE_PANELS = r'''      color: var(--muted);
      font-size: 12px;
    }
    .goal-plan-edit-grid input,
    .goal-plan-edit-grid textarea {
      width: 100%;
      min-width: 0;
      box-sizing: border-box;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--panel);
      color: var(--text);
      font: inherit;
      padding: 6px 8px;
    }
    .goal-plan-edit-grid textarea {
      min-height: 54px;
      resize: vertical;
    }
    .goal-plan-card-actions {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-top: 8px;
    }
    .goal-plan-actions {
      display: none;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .goal-plan-actions[data-visible="true"] {
      display: flex;
    }
    .decision-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .decision-line {
      margin-top: 2px;
    }
    .decision-list {
      margin-bottom: 18px;
      border: 1px solid #fecdca;
      border-left: 4px solid var(--attention);
      border-radius: 6px;
      background: #fffbfa;
      padding: 12px 14px;
      font-size: 14px;
    }
    .notification-list {
      margin-bottom: 18px;
      border: 1px solid #b2ddff;
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: #f5fbff;
      padding: 12px 14px;
      font-size: 14px;
    }
    .current-list {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--done);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .night-overview {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .overview-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      padding: 10px;
    }
    .overview-card[data-state="running"],
    .overview-card[data-state="ready"] {
      border-left: 4px solid var(--done);
    }
    .overview-card[data-state="working"] {
      border-left: 4px solid var(--working);
    }
    .overview-card[data-state="attention"] {
      border-left: 4px solid var(--attention);
    }
    .overview-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .overview-value {
      display: block;
      margin-top: 4px;
      color: var(--text);
      font-size: 22px;
      font-weight: 800;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }
    .overview-detail {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .current-list-head,
    .multi-worker-head,
    .notification-list-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .current-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 10px;
    }
    .current-subhead {
      color: var(--text);
      font-size: 13px;
      font-weight: 700;
      margin-bottom: 6px;
    }
    .current-items {
      display: grid;
      gap: 8px;
    }
    .current-item {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 8px;
      min-width: 0;
    }
    .dependency-batch {
      margin-top: 12px;
      border: 1px solid #b2ddff;
      border-radius: 6px;
      background: #eff8ff;
      padding: 10px;
    }
    .dependency-batch-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--text);
      font-weight: 800;
    }
    .dependency-batch-summary {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .dependency-batch-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-top: 8px;
    }
    .dependency-bucket {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      padding: 8px;
    }
    .dependency-bucket-title {
      color: var(--text);
      font-size: 12px;
      font-weight: 800;
      margin-bottom: 6px;
    }
    .dependency-bucket-item {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
      margin-top: 4px;
    }
    .current-title {
      color: var(--text);
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .current-detail {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .worker-detail-list {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .worker-detail-list-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .worker-detail-body {
      display: grid;
      gap: 10px;
      margin-top: 10px;
    }
    .worker-detail-card {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 10px;
    }
    .worker-detail-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
      min-width: 0;
    }
    .worker-detail-title {
      color: var(--text);
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .worker-detail-meta {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .worker-detail-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 12px;
      margin-top: 10px;
    }
    .worker-detail-field {
      min-width: 0;
    }
    .worker-detail-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .worker-detail-value {
      color: var(--text);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .worker-detail-output {
      margin: 10px 0 0;
      max-height: 180px;
      overflow: auto;
      white-space: pre-wrap;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: #344054;
      padding: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
    }
'''
