"""Base CSS for the local Supervisor dashboard."""

from __future__ import annotations


DASHBOARD_STYLE_BASE = r'''    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2933;
      --muted: #667085;
      --line: #d9dee7;
      --attention: #b42318;
      --done: #067647;
      --working: #175cd3;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      padding: 24px 28px 16px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 24px; font-weight: 700; }
    .meta { color: var(--muted); font-size: 13px; text-align: right; }
    main { padding: 20px 28px 28px; }
    .recommendation {
      margin-bottom: 18px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: var(--panel);
      font-size: 14px;
    }
    .recommendation-main {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
    }
    .llm-action {
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .llm-action.decision-request {
      border: 1px solid #fecdca;
      border-left: 4px solid var(--attention);
      border-radius: 6px;
      background: #fffbfa;
      color: #7a271a;
      padding: 8px;
    }
    .operator-focus {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--attention);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .operator-focus-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--text);
      font-weight: 800;
    }
    .focus-primary-action {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
      overflow-wrap: anywhere;
      text-align: right;
    }
    .focus-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .focus-card,
    .focus-item {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 10px;
    }
    .focus-label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .focus-value {
      display: block;
      margin-top: 3px;
      color: var(--text);
      font-size: 20px;
      line-height: 1.1;
      overflow-wrap: anywhere;
    }
    .focus-detail {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .focus-list {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .supervised-focus {
      margin-top: 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 10px;
      min-width: 0;
    }
    .supervised-focus-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      color: var(--text);
      font-weight: 800;
    }
    .focus-title {
      color: var(--text);
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .control-center {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--working);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .control-center-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .control-center-body {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .control-service {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 10px;
    }
    .control-service-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: center;
      color: var(--text);
      font-weight: 700;
    }
    .control-service-detail {
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .control-service-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 8px;
    }
    .control-message {
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .goal-queue-panel {
      margin-bottom: 18px;
      border: 1px solid var(--line);
      border-left: 4px solid var(--done);
      border-radius: 6px;
      background: var(--panel);
      padding: 12px 14px;
      font-size: 14px;
    }
    .goal-queue-head {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      font-weight: 700;
    }
    .goal-add-form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      margin-top: 10px;
    }
    .goal-add-form textarea {
      width: 100%;
      min-height: 72px;
      resize: vertical;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
      color: var(--text);
      font: inherit;
      line-height: 1.4;
    }
    .goal-add-message {
      margin-top: 6px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .goal-add-actions {
      display: flex;
      flex-direction: column;
      gap: 8px;
      align-items: stretch;
    }
    .goal-queue-list {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .goal-queue-item {
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f8fafc;
      padding: 8px;
    }
    .goal-title {
      color: var(--text);
      font-weight: 700;
      overflow-wrap: anywhere;
    }
    .goal-detail {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .goal-plan-preview {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .goal-plan-card {
      min-width: 0;
      border: 1px solid #b2ddff;
      border-radius: 6px;
      background: #eff8ff;
      padding: 10px;
    }
    .goal-plan-title {
      color: var(--text);
      font-weight: 800;
      overflow-wrap: anywhere;
    }
    .goal-plan-detail {
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .goal-plan-edit-grid {
      display: grid;
      gap: 8px;
      margin-top: 8px;
    }
    .goal-plan-edit-grid label {
      display: grid;
      gap: 3px;
'''
