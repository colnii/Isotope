"""Responsive CSS for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_STYLE_RESPONSIVE = r'''    .multi-worker-panel {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--ready);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .multi-worker-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .multi-worker-stat {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 8px;
      min-width: 0;
    }
    .multi-worker-stat span {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .multi-worker-stat strong {
      display: block;
      color: var(--text);
      font-size: 20px;
      line-height: 1.2;
    }
    .multi-worker-body {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .multi-worker-card {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 10px;
      min-width: 0;
    }
    .multi-worker-title {
      color: var(--text);
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .multi-worker-detail {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .notification-list-body {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .notification-summary {
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .notification-list-item {
      color: #1849a9;
      overflow-wrap: anywhere;
    }
    .notification-title-line {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      color: var(--text);
      font-weight: 700;
    }
    .notification-source {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .decision-list-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .decision-list-body {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .decision-list-item {
      color: #7a271a;
      overflow-wrap: anywhere;
    }
    .decision-answer-form {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .decision-answer-form textarea {
      width: 100%;
      min-height: 72px;
      resize: vertical;
      border: 1px solid #fecdca;
      border-radius: 6px;
      padding: 8px;
      color: var(--text);
      font: inherit;
      line-height: 1.4;
    }
    .decision-answer-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .decision-answer-message {
      color: var(--muted);
      font-size: 12px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
    }
    section {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--panel);
      overflow: hidden;
    }
    .group-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    h2 { margin: 0; font-size: 16px; font-weight: 700; }
    .count {
      min-width: 28px;
      text-align: center;
      border-radius: 999px;
      background: #edf1f7;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      padding: 3px 8px;
    }
    .lane-list {
      display: grid;
      gap: 0;
      min-height: 72px;
    }
    .lane {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }
    .lane:last-child { border-bottom: 0; }
    .lane-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 6px;
      font-weight: 700;
      min-width: 0;
    }
    .lane-name {
      overflow-wrap: anywhere;
      min-width: 0;
    }
    .badge {
      flex: 0 0 auto;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      background: #edf1f7;
      color: var(--muted);
    }
    .summary,
    .evidence,
    .path,
    .protocol-card,
    .managed-details,
    .command {
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .evidence {
      margin-top: 2px;
      color: #475467;
    }
    .source-line {
      margin-top: 2px;
      color: #344054;
    }
    .command {
      margin-top: 8px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .protocol-card {
      margin-top: 8px;
      border: 1px solid #fedf89;
      border-left: 4px solid #dc6803;
      border-radius: 6px;
      background: #fffbeb;
      padding: 8px;
    }
    .protocol-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .protocol-line {
      margin-top: 2px;
    }
    .managed-details {
      margin-top: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 8px;
    }
    .managed-details-title {
      color: var(--text);
      font-weight: 700;
      margin-bottom: 4px;
    }
    .managed-line {
      margin-top: 2px;
    }
    .terminal-excerpt {
      margin: 6px 0 0;
      max-height: 120px;
      overflow: auto;
      white-space: pre-wrap;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      color: #344054;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    button {
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #ffffff;
      color: var(--text);
      cursor: pointer;
      font-size: 12px;
      padding: 6px 9px;
    }
    button:hover { background: #f2f4f7; }
    button[data-action="send"] {
      border-color: #b2ddff;
      color: var(--working);
    }
    button.suggested-action {
      border-color: #175cd3;
      background: #eff8ff;
      box-shadow: 0 0 0 2px rgba(23, 92, 211, 0.14);
      font-weight: 700;
    }
    [data-group="needs_attention"] .group-head { border-top: 3px solid var(--attention); }
    [data-group="done"] .group-head { border-top: 3px solid var(--done); }
    [data-group="working"] .group-head { border-top: 3px solid var(--working); }
    .empty {
      padding: 18px 14px;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 900px) {
      header { display: block; }
      .meta { text-align: left; margin-top: 6px; }
      main { padding: 16px; }
      .grid { grid-template-columns: 1fr; }
      .night-overview { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .focus-grid { grid-template-columns: 1fr; }
      .control-center-body { grid-template-columns: 1fr; }
      .goal-add-form { grid-template-columns: 1fr; }
      .current-grid { grid-template-columns: 1fr; }
      .dependency-batch-grid { grid-template-columns: 1fr; }
      .worker-detail-grid { grid-template-columns: 1fr; }
    }
'''
